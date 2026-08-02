import sys
import os

# Reasoning: Add the project root to the path so shared modules are importable.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import json
from mistralai import Mistral
from typing import TypedDict
from langgraph.graph import StateGraph, END

from shared.config import MISTRAL_API_KEY, MODEL_NAME
from agents.pricing_agent.tools import get_price, suggest_discount, compare_competitor_price
from agents.inventory_agent.tools import check_stock, forecast_restock, flag_low_stock
from agents.risk_support_agent.tools import check_seller_risk, get_return_pattern, create_support_ticket, escalate

# Reasoning: Initialize a single Mistral client reused by all orchestrator nodes.
client = Mistral(api_key=MISTRAL_API_KEY)

# --- State Definition ---
# Reasoning: LangGraph needs a typed dict to define the graph's shared state.
# Every node reads from and writes to this state object.
class OrchestratorState(TypedDict):
    user_query: str           # The original user question
    agent_called: str         # Which tool the router decided to invoke
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
# Reasoning: This node gives Mistral the user query and all tool definitions.
# Mistral decides which tool to call and with what arguments.
def router_node(state: OrchestratorState) -> OrchestratorState:
    # Load the system prompt from the versioned prompt file based on ORCHESTRATOR_PROMPT_VERSION env var.
    prompt_ver = os.getenv("ORCHESTRATOR_PROMPT_VERSION", "v1")
    prompt_filename = f"orchestrator_{prompt_ver}.md"
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_filename)
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    # Reasoning: Build messages with system prompt + conversation history + new user query.
    messages = [{"role": "system", "content": system_prompt}]
    messages += state["messages"]
    messages.append({"role": "user", "content": state["user_query"]})

    # Reasoning: Call Mistral with the full tool list. Mistral returns tool_calls in its response.
    response = client.chat.complete(
        model=MODEL_NAME,
        tools=TOOLS,
        messages=messages
    )

    assistant_message = response.choices[0].message

    # Reasoning: Check if Mistral chose to call a tool (tool_calls will be non-empty).
    if assistant_message.tool_calls:
        tool_call = assistant_message.tool_calls[0]
        tool_name = tool_call.function.name

        # Reasoning: Mistral returns arguments as a JSON string — parse it into a dict.
        tool_args = json.loads(tool_call.function.arguments)

        # Reasoning: Call the actual Python function from our registry.
        tool_fn = TOOL_REGISTRY.get(tool_name)
        tool_result = tool_fn(**tool_args) if tool_fn else f"Tool '{tool_name}' not found."

        state["agent_called"] = tool_name
        state["tool_result"] = tool_result

        # Reasoning: Append the assistant's tool call and the tool result to message history.
        # This is required by Mistral's multi-turn format.
        state["messages"].append({"role": "user", "content": state["user_query"]})
        state["messages"].append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
        state["messages"].append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": tool_result
        })
    else:
        # Reasoning: If Mistral chose not to call a tool, capture its text response directly.
        state["agent_called"] = "none"
        state["tool_result"] = assistant_message.content
        state["messages"].append({"role": "user", "content": state["user_query"]})
        state["messages"].append({"role": "assistant", "content": assistant_message.content})

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
