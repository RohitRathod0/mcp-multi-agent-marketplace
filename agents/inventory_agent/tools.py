import os
import sys

# Reasoning: Add the parent directory to path to access the RAG retriever.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from rag.retriever import retrieve_context

# Mock inventory database
MOCK_INVENTORY = {
    "iph-15-base": {"stock": 42, "avg_sales": 120},
    "gen-hd-01": {"stock": 105, "avg_sales": 50},
    "p-tv-65": {"stock": 3, "avg_sales": 15}
}

def check_stock(product_id: str) -> str:
    """Check if an item is in stock."""
    # Reasoning: Look up the product in our mock inventory database.
    item = MOCK_INVENTORY.get(product_id.lower())
    
    if item is not None:
        return f"Product {product_id} has {item['stock']} units in stock."
    return f"Product {product_id} not found in inventory."

def forecast_restock(product_id: str) -> str:
    """Forecast if a restock is needed based on warehouse policy."""
    # Reasoning: Retrieve the warehouse policy from the vector store to ground the restock logic.
    policy = retrieve_context(query="restock forecasting rules", doc_type="policy")
    
    # Reasoning: Provide the agent with the current stock and the policy rules to make a decision.
    item = MOCK_INVENTORY.get(product_id.lower())
    if item:
        return (
            f"Current stock for {product_id} is {item['stock']}. "
            f"Average 30-day sales volume is {item['avg_sales']}.\n\n"
            f"[WAREHOUSE POLICY]\n{policy}"
        )
    return f"Product {product_id} not found for forecasting."

def flag_low_stock() -> str:
    """Scan all inventory and flag low stock items according to policy."""
    # Reasoning: Retrieve the low stock policy from the vector store.
    policy = retrieve_context(query="low stock flagging rules", doc_type="policy")
    
    # Reasoning: List all current inventory levels for the agent to evaluate against the policy.
    inventory_summary = "\n".join([f"- {sku}: {data['stock']} units" for sku, data in MOCK_INVENTORY.items()])
    
    return (
        f"Please review the following inventory and flag items based on the policy:\n\n"
        f"[CURRENT INVENTORY]\n{inventory_summary}\n\n"
        f"[WAREHOUSE POLICY]\n{policy}"
    )
