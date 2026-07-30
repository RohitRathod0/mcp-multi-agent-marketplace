from rag.vectorstore_client import get_collection

def retrieve_context(query, doc_type=None, top_k=2):
    # Reasoning: We retrieve the shared ChromaDB collection.
    collection = get_collection()
    
    # Reasoning: If a doc_type is provided, we filter the search to only that namespace.
    # This prevents the pricing agent from pulling risk-only docs, as required by the PRD.
    where_clause = {"doc_type": doc_type} if doc_type else None
    
    # Reasoning: We query the collection for the closest matching documents to our query.
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where_clause
    )
    
    # Reasoning: The results contain lists of documents and distances. We extract the documents.
    if results and results["documents"]:
        # results["documents"] is a list of lists. We take the first list for our single query.
        documents = results["documents"][0]
        # Return a combined string of the retrieved contexts.
        return "\n\n".join(documents)
    
    # Reasoning: If no results match the threshold or query, we return a fallback string.
    return "No relevant grounding context found."
