import os
import chromadb

# Reasoning: We need a singleton or a simple client to interact with the vector store.
# ChromaDB is chosen for local simplicity as it doesn't require a separate server to start.

def get_chroma_client():
    # Reasoning: We initialize a persistent ChromaDB client pointing to a local directory.
    # This allows data to persist across restarts.
    persist_directory = os.path.join(os.path.dirname(__file__), "chroma_db")
    client = chromadb.PersistentClient(path=persist_directory)
    return client

def get_collection(collection_name="marketplace_knowledge"):
    # Reasoning: We retrieve or create a single shared collection for our RAG store.
    # The PRD mentions namespacing by document type within a single shared collection.
    client = get_chroma_client()
    collection = client.get_or_create_collection(name=collection_name)
    return collection
