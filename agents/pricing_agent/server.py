from fastmcp import FastMCP
from tools import get_price, suggest_discount, compare_competitor_price

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
    # Reasoning: Start the server using stdio transport by default, which is standard for MCP.
    print("Starting Pricing Agent MCP Server...")
    mcp.run()
