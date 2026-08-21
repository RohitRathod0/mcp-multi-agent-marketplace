import os
import sys

# Reasoning: Put the project root on sys.path explicitly rather than inheriting it as a
# side effect of importing tools.py. server.py needs `shared.mcp_transport` itself, and
# depending on another module's import side effect to make that resolve is the kind of
# ordering trap that breaks the moment imports get reordered.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastmcp import FastMCP
from tools import get_price, suggest_discount, compare_competitor_price
from shared.mcp_transport import run_agent_server

# Reasoning: We initialize a FastMCP server named "pricing_agent".
# FastMCP simplifies exposing Python functions as MCP tools.
mcp = FastMCP("pricing_agent")

# Reasoning: Register the get_price function as an MCP tool.
@mcp.tool()
def mcp_get_price(product_id: str) -> str:
    """Retrieves the current baseline price for a product."""
    return get_price(product_id)

# Reasoning: Register the suggest_discount function as an MCP tool.
@mcp.tool()
def mcp_suggest_discount(product_id: str, context: str) -> str:
    """Suggests a discount strategy grounded in RAG policies and historical cases."""
    return suggest_discount(product_id, context)

# Reasoning: Register the compare_competitor_price function as an MCP tool.
@mcp.tool()
def mcp_compare_competitor_price(product_id: str) -> str:
    """Compares our price against known competitor prices."""
    return compare_competitor_price(product_id)

if __name__ == "__main__":
    # Reasoning: stdio by default (orchestrator spawns this as a subprocess), http when
    # MCP_TRANSPORT=http so this same server can run as its own container. See
    # shared/mcp_transport.py for why both transports are needed.
    run_agent_server(mcp, "pricing_agent")
