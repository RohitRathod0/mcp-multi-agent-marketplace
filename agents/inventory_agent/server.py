from fastmcp import FastMCP
from tools import check_stock, forecast_restock, flag_low_stock

# Reasoning: Initialize a FastMCP server named "inventory_agent".
mcp = FastMCP("inventory_agent")

# Reasoning: Expose the check_stock function.
@mcp.tool()
def mcp_check_stock(product_id: str) -> str:
    """Check if an item is in stock."""
    return check_stock(product_id)

# Reasoning: Expose the forecast_restock function.
@mcp.tool()
def mcp_forecast_restock(product_id: str) -> str:
    """Forecast if a restock is needed based on warehouse policy."""
    return forecast_restock(product_id)

# Reasoning: Expose the flag_low_stock function.
@mcp.tool()
def mcp_flag_low_stock() -> str:
    """Scan all inventory and flag low stock items according to policy."""
    return flag_low_stock()

if __name__ == "__main__":
    # Reasoning: Start the server using stdio transport.
    print("Starting Inventory Agent MCP Server...")
    mcp.run()
