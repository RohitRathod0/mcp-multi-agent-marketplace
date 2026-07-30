import os
import sys

# Reasoning: Add the parent directory to the path so we can import the 'rag' module.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from rag.retriever import retrieve_context

# Simulated database of product prices
MOCK_PRICES = {
    "iphone-15": 999.00,
    "generic-headphones": 49.99,
    "premium-tv": 1200.00
}

# Simulated database of competitor prices
MOCK_COMPETITOR_PRICES = {
    "iphone-15": 989.00,
    "premium-tv": 1080.00
}

def get_price(product_id: str) -> str:
    """Retrieves the current baseline price for a product."""
    # Reasoning: We look up the price in our mock database.
    price = MOCK_PRICES.get(product_id.lower())
    
    # Reasoning: If the price exists, format it nicely. Otherwise, return an error message.
    if price is not None:
        return f"The current price for {product_id} is ${price:.2f}."
    return f"Product {product_id} not found in catalog."

def suggest_discount(product_id: str, context: str) -> str:
    """Suggests a discount strategy by grounding the decision in pricing policies."""
    # Reasoning: Retrieve pricing policies to ground the discount suggestion.
    policy_context = retrieve_context(query=f"discount rules for {context}", doc_type="policy")
    
    # Reasoning: Retrieve historical cases to learn from past outcomes.
    history_context = retrieve_context(query=f"historical discount for {product_id} or similar", doc_type="historical_case")
    
    # Reasoning: We compile the contexts together to provide a comprehensive rule set for the agent.
    # The actual LLM evaluation will be done by the orchestrator or agent using this returned string.
    combined_response = (
        f"To suggest a discount for {product_id}, please refer to the following policies:\n\n"
        f"[POLICIES]\n{policy_context}\n\n"
        f"[HISTORICAL CASES]\n{history_context}\n\n"
        f"Current price is {get_price(product_id)}."
    )
    return combined_response

def compare_competitor_price(product_id: str) -> str:
    """Compares our price against known competitor prices."""
    # Reasoning: Fetch our price for the product.
    our_price = MOCK_PRICES.get(product_id.lower())
    
    # Reasoning: Fetch the competitor's price for the product.
    comp_price = MOCK_COMPETITOR_PRICES.get(product_id.lower())
    
    # Reasoning: Compare the prices and return a summary.
    if our_price and comp_price:
        diff = our_price - comp_price
        return f"Our price: ${our_price}. Competitor price: ${comp_price}. Difference: ${diff:.2f}."
    return "Competitor price data not available for this product."
