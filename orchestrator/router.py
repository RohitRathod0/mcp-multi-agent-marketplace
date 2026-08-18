import sys
import os

# Reasoning: Add the project root to the path so shared modules are importable.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import json
from mistralai import Mistral
from typing import TypedDict
from langgraph.graph import StateGraph, END

from shared.config import MISTRAL_API_KEY, MODEL_NAME
from shared.mistral_utils import call_mistral_with_retry
from orchestrator.mcp_clients import get_agent_pool, TOOL_ROUTES

# Reasoning: Initialize a single Mistral client reused by all orchestrator nodes.
client = Mistral(api_key=MISTRAL_API_KEY)

# --- State Definition ---
# Reasoning: LangGraph needs a typed dict to define the graph's shared state.
# Every node reads from and writes to this state object.
class OrchestratorState(TypedDict):
    user_query: str           # The original user question
    agent_called: str         # The first tool the router decided to invoke (kept for
                               # backward-compat with single-agent eval scoring)
    tool_result: str          # The raw output from the tool(s), concatenated in call order
    tool_calls: list          # Full trace of every tool call this turn: [{agent, tool, args, result}]
    messages: list            # Full conversation history for multi-turn support
    final_answer: str         # The synthesized, user-facing answer

# Reasoning: Cap how many tool-calling round-trips the orchestrator will make for a
# single query. Mistral can request several tools in one turn (e.g. pricing +
# inventory for a combined question) and/or ask for more tools after seeing a result
# (e.g. check_seller_risk before deciding to suggest_discount) — this loop supports
# both, bounded so a confused model can't loop forever.
MAX_TOOL_ROUNDS = 4

# --- Tool Definitions for Mistral ---
# Reasoning: Mistral uses the OpenAI-style "function" tool format.
# Each entry describes a callable tool the LLM can invoke.
TOOLS = [
    {"type": "function", "function": {"name": "get_price", "description": "Get the current price for a product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {"name": "suggest_discount", "description": "Suggest a discount for a product grounded in policy.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "context": {"type": "string"}}, "required": ["product_id", "context"]}}},
    {"type": "function", "function": {"name": "compare_competitor_price", "description": "Compare our price vs a competitor for a product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {"name": "check_stock", "description": "Check stock level for a product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {"name": "forecast_restock", "description": "Forecast if a restock is needed for a product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}}},
    {"type": "function", "function": {"name": "flag_low_stock", "description": "Scan all inventory and flag items with low stock.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "check_seller_risk", "description": "Assess risk level for a seller.", "parameters": {"type": "object", "properties": {"seller_id": {"type": "string"}}, "required": ["seller_id"]}}},
    {"type": "function", "function": {"name": "get_return_pattern", "description": "Get historical return patterns for a seller.", "parameters": {"type": "object", "properties": {"seller_id": {"type": "string"}}, "required": ["seller_id"]}}},
    {"type": "function", "function": {"name": "create_support_ticket", "description": "Create a support ticket for an order issue.", "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "issue": {"type": "string"}}, "required": ["order_id", "issue"]}}},
    {"type": "function", "function": {"name": "escalate", "description": "Escalate a ticket to a human when confidence is low.", "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]}}},
]

# --- Node: Router ---
# Reasoning: This node gives Mistral the user query and all tool definitions, then loops
# tool-calling round-trips so a single query can be resolved by multiple agents (e.g.
# "is it in stock, and should we discount it?" needs both inventory and pricing) before
# handing off to the synthesizer. Every tool call is executed as a real MCP request
# against the owning agent's subprocess via the shared MCPAgentPool — not an in-process
# function call — so pricing/inventory/risk really are independent services here.
def router_node(state: OrchestratorState) -> OrchestratorState:
    # Reasoning: Load the system prompt from the versioned prompt file based on ORCHESTRATOR_PROMPT_VERSION env var.
    prompt_ver = os.getenv("ORCHESTRATOR_PROMPT_VERSION", "v1")
    prompt_filename = f"orchestrator_{prompt_ver}.md"
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_filename)
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    # Reasoning: Build messages with system prompt + conversation history + new user query.
    messages = [{"role": "system", "content": system_prompt}]
    messages += state["messages"]
    messages.append({"role": "user", "content": state["user_query"]})

    pool = get_agent_pool()
    tool_calls_trace = []
    assistant_message = None

    for _ in range(MAX_TOOL_ROUNDS):
        # Reasoning: Call Mistral with the full tool list, retrying on rate limits (429).
        # Mistral returns tool_calls in its response — possibly more than one per turn.
        response = call_mistral_with_retry(lambda: client.chat.complete(
            model=MODEL_NAME,
            tools=TOOLS,
            messages=messages
        ))
        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            # Reasoning: Mistral is done calling tools (or never needed one) — record its
            # final text turn so the synthesizer/history sees it, then stop looping.
            messages.append({"role": "assistant", "content": assistant_message.content})
            break

        # Reasoning: Append the assistant's tool-call turn, then execute every tool it
        # asked for this round via the real MCP client pool and append each result.
        messages.append({"role": "assistant", "content": assistant_message.content, "tool_calls": assistant_message.tool_calls})
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_result = pool.call_tool(tool_name, tool_args)

            tool_calls_trace.append({
                "agent": TOOL_ROUTES.get(tool_name, ("unknown", None))[0],
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": tool_result
            })

    # Reasoning: Persist everything except the system prompt — it's reloaded fresh from
    # the versioned prompt file on every call, so keeping it out of state["messages"]
    # avoids duplicating/stacking system messages across turns.
    state["messages"] = [m for m in messages if m.get("role") != "system"]
    state["tool_calls"] = tool_calls_trace

    if tool_calls_trace:
        # Reasoning: Keep agent_called as the *first* tool for backward-compat with
        # single-agent eval scoring; tool_result concatenates every result in call
        # order so the synthesizer (and multi-agent eval checks) can see all of them.
        state["agent_called"] = tool_calls_trace[0]["tool"]
        state["tool_result"] = "\n---\n".join(c["result"] for c in tool_calls_trace)
    else:
        # Reasoning: Mistral chose not to call any tool — capture its text response directly.
        state["agent_called"] = "none"
        state["tool_result"] = assistant_message.content if assistant_message else "No tool called."

    return state

# --- Node: Synthesizer ---
# Reasoning: This node takes the tool result and asks Mistral to write a clean final answer.
def synthesizer_node(state: OrchestratorState) -> OrchestratorState:
    from orchestrator.synthesizer import synthesize
    state["final_answer"] = synthesize(state["messages"], client, MODEL_NAME)
    return state

# --- Graph Assembly ---
# Reasoning: Wire up the two nodes sequentially: router runs first, then synthesizer.
def build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("router", router_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.set_entry_point("router")
    graph.add_edge("router", "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile()

# Reasoning: Create a single compiled graph instance to reuse across requests.
orchestrator_graph = build_graph()
