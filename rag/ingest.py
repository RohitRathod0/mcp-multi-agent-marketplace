import os
import uuid
from vectorstore_client import get_collection

def ingest_directory(directory_path, doc_type):
    # Reasoning: We retrieve the shared ChromaDB collection where all documents live.
    collection = get_collection()
    
    # Reasoning: We iterate over all files in the given directory to ingest them.
    if not os.path.exists(directory_path):
        print(f"Directory {directory_path} does not exist.")
        return
        
    for filename in os.listdir(directory_path):
        if filename.endswith(".md"):
            filepath = os.path.join(directory_path, filename)
            
            # Reasoning: Read the content of the markdown file.
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Reasoning: Generate a unique ID for each document to store in ChromaDB.
            doc_id = str(uuid.uuid4())
            
            # Reasoning: We store the content along with metadata specifying its type (e.g., 'policy').
            # This enables namespaced retrieval later by filtering on 'doc_type'.
            collection.add(
                documents=[content],
                metadatas=[{"doc_type": doc_type, "source": filename}],
                ids=[doc_id]
            )
            print(f"Ingested {filename} as type {doc_type}.")

def run_ingestion():
    # Reasoning: Get the absolute path to the data directories.
    base_dir = os.path.dirname(__file__)
    policies_dir = os.path.join(base_dir, "data", "policies")
    historical_cases_dir = os.path.join(base_dir, "data", "historical_cases")
    catalog_dir = os.path.join(base_dir, "data", "catalog")
    
    # Reasoning: Ingest policies and historical cases with their respective doc_type tags.
    ingest_directory(policies_dir, "policy")
    ingest_directory(historical_cases_dir, "historical_case")
    ingest_directory(catalog_dir, "catalog")
    
    print("Ingestion complete.")

if __name__ == "__main__":
    run_ingestion()
