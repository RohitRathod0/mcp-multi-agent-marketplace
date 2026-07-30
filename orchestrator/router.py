import sys
import os

# Reasoning: Add the project root to the path so shared modules are importable.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import anthropic
from typing import TypedDict
from langgraph.graph import StateGraph, END

from shared.config import ANTHROPIC_API_KEY, MODEL_NAME
from agents.pricing_agent.tools import get_price, suggest_discount, compare_competitor_price
from agents.inventory_agent.tools import check_stock, forecast_restock, flag_low_stock
from agents.risk_support_agent.tools import check_seller_risk, get_return_pattern, create_support_ticket, escalate

# Reasoning: Initialize a single Anthropic client reused by all orchestrator nodes.
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# --- State Definition ---
# Reasoning: LangGraph needs a typed dict to define the graph's shared state.
# Every node reads from and writes to this state object.
class OrchestratorState(TypedDict):
    user_query: str           # The original user question
    agent_called: str         # Which agent the router decided to invoke
    tool_result: str          # The raw output from the tool
    messages: list            # Full conversation history for multi-turn support
    final_answer: str         # The synthesized, user-facing answer

# --- Tool Registry ---
# Reasoning: A flat dict mapping tool names to their functions makes routing trivial.
TOOL_REGISTRY = {
    "get_price": get_price,
    "suggest_discount": suggest_discount,
    "compare_competitor_price": compare_competitor_price,
    "check_stock": check_stock,
    "forecast_restock": forecast_restock,
    "flag_low_stock": flag_low_stock,
    "check_seller_risk": check_seller_risk,
    "get_return_pattern": get_return_pattern,
    "create_support_ticket": create_support_ticket,
    "escalate": escalate,
}

# --- Tool Definitions for Claude ---
# Reasoning: We tell Claude exactly what tools it can call.
# These match the signatures in our agent tools.py files.
TOOLS = [
    {"name": "get_price", "description": "Get the current price for a product.", "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "suggest_discount", "description": "Suggest a discount for a product grounded in policy.", "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}, "context": {"type": "string"}}, "required": ["product_id", "context"]}},
    {"name": "compare_competitor_price", "description": "Compare our price vs a competitor for a product.", "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "check_stock", "description": "Check stock level for a product.", "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "forecast_restock", "description": "Forecast if a restock is needed for a product.", "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "flag_low_stock", "description": "Scan all inventory and flag items with low stock.", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "check_seller_risk", "description": "Assess risk level for a seller.", "input_schema": {"type": "object", "properties": {"seller_id": {"type": "string"}}, "required": ["seller_id"]}},
    {"name": "get_return_pattern", "description": "Get historical return patterns for a seller.", "input_schema": {"type": "object", "properties": {"seller_id": {"type": "string"}}, "required": ["seller_id"]}},
    {"name": "create_support_ticket", "description": "Create a support ticket for an order issue.", "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}, "issue": {"type": "string"}}, "required": ["order_id", "issue"]}},
    {"name": "escalate", "description": "Escalate a ticket to a human when confidence is low.", "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]}},
]

# --- Node: Router ---
# Reasoning: This node gives Claude the user query and all tool definitions.
# Claude decides which tool to call and with what arguments.
def router_node(state: OrchestratorState) -> OrchestratorState:
    # Load the system prompt from the versioned prompt file.
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "orchestrator_v1.md")
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    # Reasoning: Add the latest user message to conversation history.
    state["messages"].append({"role": "user", "content": state["user_query"]})

    # Reasoning: Call Claude with the full tool list. Claude returns a tool_use block.
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        system=system_prompt,
        tools=TOOLS,
        messages=state["messages"]
    )

    # Reasoning: Find the tool_use block in Claude's response.
    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use_block:
        tool_name = tool_use_block.name
        tool_args = tool_use_block.input

        # Reasoning: Call the actual Python function from our registry.
        tool_fn = TOOL_REGISTRY.get(tool_name)
        tool_result = tool_fn(**tool_args) if tool_fn else f"Tool '{tool_name}' not found."

        state["agent_called"] = tool_name
        state["tool_result"] = tool_result

        # Reasoning: Record Claude's tool call and the result in message history for context.
        state["messages"].append({"role": "assistant", "content": response.content})
        state["messages"].append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_block.id, "content": tool_result}]
        })
    else:
        # Reasoning: If Claude chose not to call a tool, capture its text response directly.
        state["agent_called"] = "none"
        state["tool_result"] = next((b.text for b in response.content if hasattr(b, "text")), "")

    return state

# --- Node: Synthesizer ---
# Reasoning: This node takes the tool result and asks Claude to write a clean, cited final answer.
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
