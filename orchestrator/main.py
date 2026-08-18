import sys
import os

# Reasoning: Add project root to path.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from orchestrator.router import orchestrator_graph
from orchestrator.mcp_clients import get_agent_pool

# Reasoning: Initialize FastAPI app. This is the HTTP interface to our LangGraph orchestrator.
app = FastAPI(title="MCP Marketplace Orchestrator")

# Reasoning: Allow the React frontend (running on a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def warm_mcp_pool():
    # Reasoning: Connecting to the 3 agent servers (each pays its own chromadb import
    # cost) takes on the order of a minute — pay that once at server startup instead
    # of stalling whichever request happens to arrive first.
    get_agent_pool()

@app.on_event("shutdown")
def close_mcp_pool():
    get_agent_pool().shutdown()

class QueryRequest(BaseModel):
    query: str

class ToolCallTrace(BaseModel):
    agent: str
    tool: str
    args: dict[str, Any]
    result: str

class QueryResponse(BaseModel):
    answer: str
    agent_called: str      # first tool called this turn (back-compat / quick summary)
    tool_result: str
    tool_calls: list[ToolCallTrace]  # full multi-agent trace: every tool call this turn, in order

@app.post("/query", response_model=QueryResponse)
def run_query(request: QueryRequest):
    """Accepts a natural language query and runs it through the LangGraph orchestrator."""
    # Reasoning: Build the initial state for the graph run.
    initial_state = {
        "user_query": request.query,
        "agent_called": "",
        "tool_result": "",
        "tool_calls": [],
        "messages": [],
        "final_answer": ""
    }

    # Reasoning: Run the compiled LangGraph and return the final state.
    result = orchestrator_graph.invoke(initial_state)

    return QueryResponse(
        answer=result["final_answer"],
        agent_called=result["agent_called"],
        tool_result=result["tool_result"],
        tool_calls=result.get("tool_calls", [])
    )

@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
