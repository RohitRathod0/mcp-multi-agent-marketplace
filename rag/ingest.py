import os
import sys

# Reasoning: Support both `python rag/ingest.py` (from the project root) and
# `python ingest.py` (from inside rag/), which previously only worked the second way.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vectorstore_client import get_collection, reset_collection


def ingest_directory(directory_path, doc_type):
    # Reasoning: We retrieve the shared ChromaDB collection where all documents live.
    collection = get_collection()

    # Reasoning: We iterate over all files in the given directory to ingest them.
    if not os.path.exists(directory_path):
        print(f"Directory {directory_path} does not exist.")
        return

    for filename in sorted(os.listdir(directory_path)):
        if filename.endswith(".md"):
            filepath = os.path.join(directory_path, filename)

            # Reasoning: Read the content of the markdown file.
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Reasoning: Derive the ID from the document's identity (type + filename)
            # instead of a fresh uuid4 per run. A random ID meant every re-ingest ADDED a
            # second copy of every document rather than replacing it — the store had
            # grown to 8 entries from 6 source files that way. Duplicates are not merely
            # untidy: with a small top_k, one document's two copies can occupy every
            # retrieval slot and silently halve the grounding an agent actually sees.
            doc_id = f"{doc_type}:{filename}"

            # Reasoning: upsert, not add — makes re-running ingestion idempotent.
            collection.upsert(
                documents=[content],
                metadatas=[{"doc_type": doc_type, "source": filename}],
                ids=[doc_id],
            )
            print(f"Ingested {filename} as type {doc_type} (id={doc_id}).")


def run_ingestion(reset=True):
    # Reasoning: Get the absolute path to the data directories.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    policies_dir = os.path.join(base_dir, "data", "policies")
    historical_cases_dir = os.path.join(base_dir, "data", "historical_cases")
    catalog_dir = os.path.join(base_dir, "data", "catalog")

    # Reasoning: Deterministic IDs make ingestion idempotent going forward, but they
    # cannot clean up the random-UUID duplicates an earlier run already wrote. Rebuilding
    # from empty guarantees the store matches rag/data/ exactly, and also drops documents
    # whose source file has since been deleted or renamed.
    if reset:
        reset_collection()
        print("Collection reset — rebuilding from rag/data/.")

    # Reasoning: Ingest policies and historical cases with their respective doc_type tags.
    ingest_directory(policies_dir, "policy")
    ingest_directory(historical_cases_dir, "historical_case")
    ingest_directory(catalog_dir, "catalog")

    collection = get_collection()
    print(f"Ingestion complete. Collection now holds {collection.count()} documents.")


if __name__ == "__main__":
    run_ingestion()
