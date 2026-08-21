import asyncio
import os
import sys
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

# Reasoning: Each domain agent is a *separate process* speaking MCP over stdio — this
# module is the orchestrator's MCP *client*, the same way Claude Desktop or any other
# MCP host would talk to these servers. Previously the orchestrator imported the agent
# tool functions directly and called them in-process, which defeated the whole point of
# having independent MCP servers. This pool spawns each agent as a real subprocess and
# routes every tool call through the MCP protocol (initialize -> list_tools -> call_tool).
AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents")

AGENT_SERVERS = {
    "pricing": os.path.join(AGENTS_DIR, "pricing_agent"),
    "inventory": os.path.join(AGENTS_DIR, "inventory_agent"),
    "risk_support": os.path.join(AGENTS_DIR, "risk_support_agent"),
}

# Reasoning: Two transports, one client. Under stdio (the default) the orchestrator spawns
# each agent as a child process — which only works when client and server share a machine
# and a process tree. Under Docker Compose each agent is its own container, so there is no
# child process to pipe to and the connection has to be a network one. MCP_TRANSPORT picks
# which, and it is the *only* thing that differs: the same agent code, the same
# initialize -> list_tools -> call_tool protocol, and every layer above this file is
# unchanged either way.
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").lower()

AGENT_URLS = {
    "pricing": os.getenv("PRICING_AGENT_URL", "http://localhost:8001/mcp"),
    "inventory": os.getenv("INVENTORY_AGENT_URL", "http://localhost:8002/mcp"),
    "risk_support": os.getenv("RISK_SUPPORT_AGENT_URL", "http://localhost:8003/mcp"),
}

# Reasoning: Maps the friendly tool name the LLM sees (matches TOOLS schema + eval set)
# to which agent server hosts it and what that server registered the tool as.
TOOL_ROUTES = {
    "get_price": ("pricing", "mcp_get_price"),
    "suggest_discount": ("pricing", "mcp_suggest_discount"),
    "compare_competitor_price": ("pricing", "mcp_compare_competitor_price"),
    "check_stock": ("inventory", "mcp_check_stock"),
    "forecast_restock": ("inventory", "mcp_forecast_restock"),
    "flag_low_stock": ("inventory", "mcp_flag_low_stock"),
    "check_seller_risk": ("risk_support", "mcp_check_seller_risk"),
    "get_return_pattern": ("risk_support", "mcp_get_return_pattern"),
    "create_support_ticket": ("risk_support", "mcp_create_support_ticket"),
    "escalate": ("risk_support", "mcp_escalate"),
}


async def _wait_for_http(url: str, agent_name: str, timeout: float = 120.0) -> None:
    """Block until an agent's HTTP MCP endpoint is accepting connections."""
    import httpx

    deadline = asyncio.get_running_loop().time() + timeout
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=5.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                # Reasoning: Any HTTP status at all proves the server is up and listening.
                # A bare GET on an MCP streamable-http endpoint is *expected* to be
                # rejected (no session, wrong method/accept header) — 400/405/406 are
                # success signals here, so status code is deliberately not checked. Only
                # a transport-level failure means "not ready yet".
                await client.get(url)
                return
            except httpx.HTTPError as e:
                last_error = e
                await asyncio.sleep(1.0)

    raise TimeoutError(
        f"Agent '{agent_name}' at {url} never became reachable within {timeout:.0f}s "
        f"(last error: {last_error})"
    )


class MCPAgentPool:
    """
    Owns one persistent MCP client connection per agent server, kept alive for the
    life of the process. Spawning a fresh subprocess per tool call (the "obvious" sync
    approach) would make every query pay multi-second startup cost x3 servers, so instead
    a single background thread runs the asyncio event loop that owns all 3 stdio
    connections, and sync callers (FastAPI handlers, the eval harness, LangGraph nodes)
    submit work to it via run_coroutine_threadsafe and block for the result.
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._sessions: dict[str, ClientSession] = {}
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._shutdown_event: asyncio.Event | None = None
        self._start_error: Exception | None = None
        print(f"MCPAgentPool: connecting to pricing/inventory/risk_support agent servers "
              f"over {MCP_TRANSPORT} (each imports chromadb — first connect can take up "
              f"to ~1 min)...", file=sys.stderr)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        # Reasoning: Each agent subprocess pays its own Python startup + chromadb import
        # cost, measured up to ~54s even connecting all 3 concurrently, so give this a
        # generous ceiling — but never silently proceed on timeout. A prior version let
        # a timed-out wait() fall through as if startup had succeeded, leaving
        # self._sessions partially populated; the first tool call routed to a
        # not-yet-connected agent then failed with a bare KeyError instead of a clear
        # error. Failing loudly here is the whole fix. This cost is paid once per
        # process lifetime — the pool is a singleton reused for every later call.
        # Reasoning: Under http this outer wait must outlast _wait_for_http's own 120s
        # ceiling, otherwise it fires first and reports a generic timeout instead of the
        # inner error naming which agent URL was unreachable — the strictly more useful
        # message when a container fails to come up.
        startup_timeout = float(os.getenv("MCP_STARTUP_TIMEOUT", "180" if MCP_TRANSPORT == "http" else "120"))
        if not self._ready.wait(timeout=startup_timeout):
            raise TimeoutError(
                f"MCPAgentPool: agent servers did not become ready within {startup_timeout:.0f}s"
            )
        if self._start_error:
            raise self._start_error
        print("MCPAgentPool: all agent servers connected.", file=sys.stderr)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._closed.set()

    async def _main(self):
        # Reasoning: anyio task groups (used internally by stdio_client) require the
        # same asyncio task to enter and exit a context manager. Keeping connect,
        # idle-wait, and teardown all inside this one coroutine/task — instead of
        # closing the stack from a separately-scheduled coroutine — is what makes
        # a clean shutdown possible instead of a "different task" RuntimeError.
        self._shutdown_event = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                async def connect(agent_name: str, agent_dir: str):
                    if MCP_TRANSPORT == "http":
                        url = AGENT_URLS[agent_name]
                        # Reasoning: Wait for the port to answer *before* opening the MCP
                        # connection rather than retrying the connection itself. A retry
                        # loop around enter_async_context would re-register a new context
                        # on the exit stack for every failed attempt, leaking the earlier
                        # half-open ones; pre-flighting keeps the real connect a single
                        # attempt. Containers legitimately need this window — each agent
                        # imports chromadb before it binds its port.
                        await _wait_for_http(url, agent_name)
                        # Reasoning: streamablehttp_client yields a 3-tuple (the third is
                        # a session-id getter), unlike stdio_client's 2-tuple.
                        read, write, _ = await stack.enter_async_context(streamablehttp_client(url))
                    else:
                        # Reasoning: Launch "python server.py" with cwd set to the agent's
                        # own directory, matching how each agent is meant to run
                        # standalone/in its own container — server.py does
                        # `from tools import ...`, a bare import that only resolves when
                        # the agent directory is on sys.path.
                        params = StdioServerParameters(
                            command=sys.executable,
                            args=["server.py"],
                            cwd=agent_dir,
                        )
                        read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self._sessions[agent_name] = session

                # Reasoning: Connect to all 3 agent servers concurrently rather than one
                # at a time — each subprocess pays its own Python + chromadb import cost,
                # and doing that sequentially is what let 3x that latency stack up
                # against the readiness timeout above.
                await asyncio.gather(*(connect(name, path) for name, path in AGENT_SERVERS.items()))

                self._ready.set()
                await self._shutdown_event.wait()
        except Exception as e:
            self._start_error = e
            self._ready.set()

    def call_tool(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> str:
        """Sync entry point: route a tool call to the correct agent server over MCP."""
        if tool_name not in TOOL_ROUTES:
            return f"Tool '{tool_name}' not found."
        agent_name, mcp_tool_name = TOOL_ROUTES[tool_name]

        async def _call():
            session = self._sessions[agent_name]
            result = await session.call_tool(mcp_tool_name, arguments)
            # Reasoning: MCP tool results are a list of content blocks; our agents only
            # ever return plain text, so join the text blocks into a single string to
            # keep the rest of the orchestrator (built around plain strings) unchanged.
            return "\n".join(block.text for block in result.content if hasattr(block, "text"))

        future = asyncio.run_coroutine_threadsafe(_call(), self._loop)
        return future.result(timeout=timeout)

    def shutdown(self):
        # Reasoning: Signal the owning task (still parked in _main on the event) to
        # fall through and close the AsyncExitStack itself, in its own task — the
        # only safe way to tear down the nested anyio task groups from stdio_client.
        if self._shutdown_event is not None:
            self._loop.call_soon_threadsafe(self._shutdown_event.set)
        self._closed.wait(timeout=10)


# Reasoning: One shared pool per process, connections opened lazily on first use and
# reused for every subsequent request — this is what makes "real MCP calls" viable
# inside a synchronous request/eval loop instead of prohibitively slow.
_pool: MCPAgentPool | None = None
_pool_lock = threading.Lock()


def get_agent_pool() -> MCPAgentPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = MCPAgentPool()
    return _pool
