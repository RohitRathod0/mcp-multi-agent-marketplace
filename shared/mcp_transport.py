import os
import sys

# Reasoning: Every agent is a standalone MCP server that has to run two different ways,
# and the difference is not cosmetic — it is the whole reason Phase 6 needed a code change:
#
#   stdio (default) - the orchestrator spawns the agent as a child process and speaks
#                     JSON-RPC over its stdin/stdout. This is how local dev, standalone
#                     agent testing, and the eval harness all work, and it stays the
#                     default so none of those workflows change.
#   http            - the agent binds a TCP port and is reached over the network. A pipe
#                     to a parent process cannot cross a container boundary, so "each MCP
#                     server in its own container" is only possible over a network
#                     transport.
#
# Keeping both behind one env var means the exact same server.py is the thing running in
# both cases — the container is not a different, parallel implementation of the agent.
DEFAULT_PORTS = {
    "pricing_agent": 8001,
    "inventory_agent": 8002,
    "risk_support_agent": 8003,
}


def run_agent_server(mcp, agent_name: str) -> None:
    """Start an agent's FastMCP server on the transport selected by MCP_TRANSPORT."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        # Reasoning: Log to stderr, never stdout — under stdio transport stdout IS the
        # JSON-RPC channel, and a stray print() there corrupts the protocol stream.
        print(f"Starting {agent_name} MCP server (stdio)...", file=sys.stderr)
        mcp.run()
        return

    if transport == "http":
        port = int(os.getenv("MCP_PORT", DEFAULT_PORTS[agent_name]))
        # Reasoning: Bind 0.0.0.0, not FastMCP's 127.0.0.1 default. Inside a container
        # a loopback-only bind is unreachable from any other container — the port would
        # be published but nothing could ever connect to it.
        print(f"Starting {agent_name} MCP server (http) on 0.0.0.0:{port}...", file=sys.stderr)
        mcp.run(transport="http", host="0.0.0.0", port=port)
        return

    raise ValueError(
        f"Unknown MCP_TRANSPORT={transport!r}. Expected 'stdio' (default) or 'http'."
    )
