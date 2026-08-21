import os
import sys

# Reasoning: Put the project root on sys.path explicitly rather than inheriting it as a
# side effect of importing tools.py — server.py needs `shared.mcp_transport` itself.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastmcp import FastMCP
from tools import check_seller_risk, get_return_pattern, create_support_ticket, escalate
from shared.mcp_transport import run_agent_server

# Reasoning: Initialize a FastMCP server named "risk_support_agent".
mcp = FastMCP("risk_support_agent")

# Reasoning: Expose check_seller_risk tool.
@mcp.tool()
def mcp_check_seller_risk(seller_id: str) -> str:
    """Assess risk level for a seller based on fraud policies."""
    return check_seller_risk(seller_id)

# Reasoning: Expose get_return_pattern tool.
@mcp.tool()
def mcp_get_return_pattern(seller_id: str) -> str:
    """Fetch historical flagged return patterns for a seller."""
    return get_return_pattern(seller_id)

# Reasoning: Expose create_support_ticket tool.
@mcp.tool()
def mcp_create_support_ticket(order_id: str, issue: str) -> str:
    """Create a support ticket for a user issue."""
    return create_support_ticket(order_id, issue)

# Reasoning: Expose escalate tool. This acts as a circuit breaker for the LLM.
@mcp.tool()
def mcp_escalate(ticket_id: str) -> str:
    """Escalate a ticket to a human when confidence in policy is low."""
    return escalate(ticket_id)

if __name__ == "__main__":
    # Reasoning: stdio by default (orchestrator spawns this as a subprocess), http when
    # MCP_TRANSPORT=http so this same server can run as its own container.
    run_agent_server(mcp, "risk_support_agent")
