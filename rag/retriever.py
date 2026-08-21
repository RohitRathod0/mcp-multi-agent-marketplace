import os
import re
from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from rag.vectorstore_client import get_collection

# Reasoning: The grounding floor, calibrated against the real corpus rather than guessed.
# Measured top-1 cosine similarity on this store: in-domain queries scored 0.474-0.710,
# out-of-domain queries ("how do I bake sourdough bread", "capital city of France")
# scored -0.019-0.099. 0.30 sits in the empty band between those two clusters with
# roughly 0.17 of margin on each side. Re-measure if the corpus changes materially —
# a threshold inherited from a different corpus is just a guess wearing a number.
MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.30"))

# Reasoning: Standard Reciprocal Rank Fusion constant. RRF combines rankings by position
# instead of by score, which is exactly what is needed here: BM25 scores are unbounded
# term-frequency sums and cosine similarities live in [-1, 1], so fusing them numerically
# would require an arbitrary normalisation that silently favours whichever scale is larger.
RRF_K = 60

INSUFFICIENT_GROUNDING = (
    "INSUFFICIENT_GROUNDING: no document in the knowledge base was similar enough to this "
    "query to serve as grounding. Do not answer from general knowledge — say the "
    "information is not available in the knowledge base, or escalate to a human."
)


def _tokenize(text: str) -> list[str]:
    # Reasoning: BM25 is a lexical matcher, so it needs tokens rather than raw text.
    # Lowercased alphanumeric runs are enough for a small curated corpus of policy
    # documents; no stemmer, because exact policy terms ("markdown", "restock",
    # "escalate") are precisely the words that should match literally.
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class RetrievalResult:
    """Retrieved context plus the scores that justify trusting it."""

    documents: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    similarities: list[float] = field(default_factory=list)
    # Reasoning: Confidence is the best semantic similarity found, kept as a first-class
    # number rather than an adjective in a prompt. This is what makes "confidence-gated"
    # a property of the code instead of a hopeful instruction to the model.
    confidence: float = 0.0
    is_grounded: bool = False

    def confidence_note(self) -> str:
        """A self-describing confidence label for tool output."""
        # Reasoning: The audit caught the model inventing a threshold twice — "below the
        # 0.8 threshold" and "below the required threshold of 0.7", when the real floor is
        # 0.30. Both happened because tool output showed a confidence number with no
        # threshold beside it, and an unexplained number invites a plausible-sounding
        # companion. Stating the actual threshold and verdict removes the gap the model
        # was filling in for itself.
        verdict = "PASSED" if self.is_grounded else "BELOW THRESHOLD"
        return f"grounding confidence {self.confidence:.2f} vs threshold {MIN_SIMILARITY:.2f} — {verdict}"

    def as_context(self) -> str:
        """Render as the grounding string an agent hands to the model."""
        if not self.is_grounded:
            return INSUFFICIENT_GROUNDING
        # Reasoning: Label every passage with its source file and similarity. The PRD
        # requires answers to be traceable to retrieved context, and a citation the model
        # can actually see is what makes that possible downstream.
        blocks = [
            f"[Source: {src} | similarity {sim:.2f}]\n{doc}"
            for doc, src, sim in zip(self.documents, self.sources, self.similarities)
        ]
        return "\n\n".join(blocks)


def retrieve(query: str, doc_type: str | None = None, top_k: int = 3) -> RetrievalResult:
    """Hybrid (BM25 + embedding) retrieval with a minimum-similarity grounding gate."""
    collection = get_collection()

    # Reasoning: Namespacing by doc_type, as the PRD requires — this is what stops the
    # pricing agent from retrieving risk-only documents. Applied to BOTH retrieval arms,
    # not just the vector one, or the lexical arm would become a hole in the same wall.
    where_clause = {"doc_type": doc_type} if doc_type else None

    candidates = collection.get(where=where_clause, include=["documents", "metadatas"])
    doc_ids = candidates["ids"]
    if not doc_ids:
        return RetrievalResult()

    docs_by_id = dict(zip(doc_ids, candidates["documents"]))
    source_by_id = {i: m.get("source", "unknown") for i, m in zip(doc_ids, candidates["metadatas"])}

    # --- Arm 1: dense/embedding retrieval -----------------------------------------
    # Reasoning: Ask for every candidate in the namespace, not top_k. Fusion needs a
    # ranking over the same pool from both arms; truncating here would make a document
    # BM25 ranks first invisible to the fusion simply because the vector arm dropped it.
    vector_hits = collection.query(
        query_texts=[query],
        n_results=len(doc_ids),
        where=where_clause,
    )
    vector_ids = vector_hits["ids"][0]
    # Reasoning: The collection uses cosine space, so distance = 1 - cosine_similarity.
    similarity_by_id = {
        i: 1.0 - d for i, d in zip(vector_ids, vector_hits["distances"][0])
    }
    vector_rank = {doc_id: rank for rank, doc_id in enumerate(vector_ids)}

    # --- Arm 2: sparse/lexical retrieval (BM25) ------------------------------------
    # Reasoning: Built per call rather than cached. The corpus is a handful of curated
    # policy documents, so indexing cost is negligible next to embedding the query, and
    # skipping the cache means a re-ingest is picked up immediately instead of leaving a
    # long-running agent server serving a stale index.
    bm25_ids = list(doc_ids)
    bm25 = BM25Okapi([_tokenize(docs_by_id[i]) for i in bm25_ids])
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_order = sorted(range(len(bm25_ids)), key=lambda i: bm25_scores[i], reverse=True)
    bm25_rank = {bm25_ids[idx]: rank for rank, idx in enumerate(bm25_order)}

    # --- Fusion --------------------------------------------------------------------
    def rrf_score(doc_id: str) -> float:
        score = 0.0
        if doc_id in vector_rank:
            score += 1.0 / (RRF_K + vector_rank[doc_id])
        if doc_id in bm25_rank:
            score += 1.0 / (RRF_K + bm25_rank[doc_id])
        return score

    ranked_ids = sorted(doc_ids, key=rrf_score, reverse=True)[:top_k]

    # Reasoning: Confidence is measured on the embedding arm only. BM25 scores have no
    # absolute meaning — a large one just means a rare term repeated — whereas cosine
    # similarity is comparable across queries, which is the property a fixed threshold
    # depends on. So lexical matching can reorder results, but it cannot on its own
    # convince the system that an unrelated document counts as grounding.
    best_similarity = max((similarity_by_id.get(i, -1.0) for i in ranked_ids), default=-1.0)
    is_grounded = best_similarity >= MIN_SIMILARITY

    if not is_grounded:
        # Reasoning: Return the score but no documents. Handing back weak passages
        # "just in case" is exactly how an unrelated document ends up quoted as fact —
        # the PRD's stated failure mode for this component.
        return RetrievalResult(confidence=max(best_similarity, 0.0), is_grounded=False)

    # Reasoning: Drop individually weak passages even when the best hit clears the bar,
    # so a strong first result cannot smuggle in an irrelevant second one.
    kept = [i for i in ranked_ids if similarity_by_id.get(i, -1.0) >= MIN_SIMILARITY]

    return RetrievalResult(
        documents=[docs_by_id[i] for i in kept],
        sources=[source_by_id[i] for i in kept],
        similarities=[similarity_by_id[i] for i in kept],
        confidence=best_similarity,
        is_grounded=True,
    )


def retrieve_context(query: str, doc_type: str | None = None, top_k: int = 3) -> str:
    """Backwards-compatible string interface used by the agent tools."""
    # Reasoning: Agent tools were written against a plain-string return, so the shape of
    # this function is unchanged. What changed is that a weakly-matched query now yields
    # INSUFFICIENT_GROUNDING instead of the closest document regardless of how unrelated
    # it was — the actual anti-hallucination requirement from PRD section 7.
    return retrieve(query, doc_type=doc_type, top_k=top_k).as_context()
