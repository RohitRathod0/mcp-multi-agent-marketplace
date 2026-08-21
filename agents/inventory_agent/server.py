import os
import sys

# Reasoning: Put the project root on sys.path explicitly rather than inheriting it as a
# side effect of importing tools.py — server.py needs `shared.mcp_transport` itself.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastmcp import FastMCP
from tools import check_stock, forecast_restock, flag_low_stock
from shared.mcp_transport import run_agent_server

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
    # Reasoning: stdio by default (orchestrator spawns this as a subprocess), http when
    # MCP_TRANSPORT=http so this same server can run as its own container.
    run_agent_server(mcp, "inventory_agent")
