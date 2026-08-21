import os
import chromadb

# Reasoning: We need a singleton or a simple client to interact with the vector store.
# ChromaDB is chosen for local simplicity as it doesn't require a separate server to start.

COLLECTION_NAME = "marketplace_knowledge"


def get_chroma_client():
    # Reasoning: We initialize a persistent ChromaDB client pointing to a local directory.
    # This allows data to persist across restarts.
    persist_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
    client = chromadb.PersistentClient(path=persist_directory)
    return client


def get_collection(collection_name=COLLECTION_NAME):
    # Reasoning: We retrieve or create a single shared collection for our RAG store.
    # The PRD mentions namespacing by document type within a single shared collection.
    client = get_chroma_client()
    collection = client.get_or_create_collection(
        name=collection_name,
        # Reasoning: Cosine, not ChromaDB's default squared-L2. The grounding threshold is
        # expressed as a similarity in [0, 1], which is only meaningful and stable if the
        # index scores that way — a raw L2 distance has no fixed upper bound to calibrate
        # a threshold against. This is set at creation time, so changing it requires a
        # re-ingest (rag/ingest.py rebuilds from empty, which handles that).
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def reset_collection(collection_name=COLLECTION_NAME):
    """Drop and recreate the collection so ingestion can rebuild it from scratch."""
    # Reasoning: Used by rag/ingest.py to guarantee the store matches rag/data/ exactly,
    # clearing out both duplicate entries from earlier random-ID runs and documents whose
    # source file no longer exists.
    client = get_chroma_client()
    try:
        client.delete_collection(name=collection_name)
    except Exception:
        # Reasoning: Nothing to delete on a first run — not an error worth failing on.
        pass
    return get_collection(collection_name)
