import os
import sys

# Reasoning: Add the parent directory to path to access the RAG retriever.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from rag.retriever import retrieve_context

# Mock databases for Risk & Support
MOCK_SELLERS = {
    "techworld-99": {"return_rate_pct": 22, "complaints": 4},
    "audioking": {"return_rate_pct": 5, "complaints": 0}
}
MOCK_TICKETS = {}

def check_seller_risk(seller_id: str) -> str:
    """Assess risk level for a seller based on fraud policies."""
    # Reasoning: Retrieve the risk policy for grounding.
    policy = retrieve_context(query="seller risk assessment", doc_type="policy")
    
    # Reasoning: Provide the seller metrics and the policy to the LLM agent.
    seller_data = MOCK_SELLERS.get(seller_id.lower())
    if seller_data:
        return (
            f"Seller {seller_id} data: Return rate: {seller_data['return_rate_pct']}%, "
            f"Complaints: {seller_data['complaints']}.\n\n"
            f"[FRAUD POLICY]\n{policy}"
        )
    return f"No risk data found for seller {seller_id}."

def get_return_pattern(seller_id: str) -> str:
    """Fetch historical flagged return patterns for a seller."""
    # Reasoning: Retrieve historical cases to spot patterns.
    history = retrieve_context(query=f"fraud history for {seller_id}", doc_type="historical_case")
    return f"Historical return patterns related to {seller_id}:\n{history}"

def create_support_ticket(order_id: str, issue: str) -> str:
    """Create a support ticket for a user issue."""
    # Reasoning: Just mock the ticket creation.
    ticket_id = f"TICK-{len(MOCK_TICKETS) + 1}"
    MOCK_TICKETS[ticket_id] = {"order_id": order_id, "issue": issue, "status": "open"}
    return f"Created support ticket {ticket_id} for order {order_id}."

def escalate(ticket_id: str) -> str:
    """Escalate a ticket to a human when confidence is low."""
    # Reasoning: Fulfill the PRD's 'escalation gating' requirement by providing a direct tool to hand off.
    if ticket_id in MOCK_TICKETS:
        MOCK_TICKETS[ticket_id]["status"] = "escalated_to_human"
        return f"Ticket {ticket_id} successfully escalated to a human agent. Please inform the user."
    return f"Failed to escalate. Ticket {ticket_id} not found."
