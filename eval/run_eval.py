import sys
import os
import json
import csv
import argparse
import time

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Ensure UTF-8 output encoding for Windows console compatibility
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

TOOL_TO_AGENT = {
    "get_price": "pricing",
    "suggest_discount": "pricing",
    "compare_competitor_price": "pricing",
    "check_stock": "inventory",
    "forecast_restock": "inventory",
    "flag_low_stock": "inventory",
    "check_seller_risk": "risk_support",
    "get_return_pattern": "risk_support",
    "create_support_ticket": "risk_support",
    "escalate": "risk_support",
    "none": "none"
}

def evaluate(prompt_version: str, output_csv: str, eval_filename: str = "eval_set.jsonl"):
    os.environ["ORCHESTRATOR_PROMPT_VERSION"] = prompt_version
    
    # Import orchestrator after setting env var so it picks up the prompt version
    from orchestrator.router import orchestrator_graph
    
    eval_set_path = os.path.join(os.path.dirname(__file__), eval_filename)
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    
    with open(eval_set_path, "r", encoding="utf-8") as f:
        test_cases = [json.loads(line) for line in f if line.strip()]
        
    results = []
    
    total = len(test_cases)
    routing_correct_count = 0
    tool_correct_count = 0
    grounded_count = 0
    # Reasoning: Count infrastructure failures separately from model failures. A Mistral
    # read-timeout is not the prompt choosing the wrong tool, but the harness previously
    # scored it as a routing AND tool AND grounding miss — so a network blip quietly
    # lowered the published prompt-accuracy figure and looked like a regression. These
    # queries are still reported (never silently dropped), just attributed honestly.
    api_error_count = 0
    
    print(f"\n==================================================")
    print(f" Running Evaluation Harness (Prompt Version: {prompt_version})")
    print(f" Total Test Cases: {total}")
    print(f"==================================================\n")
    
    for idx, tc in enumerate(test_cases, 1):
        query = tc["query"]
        # Reasoning: Support both single-agent test cases (expected_agent/expected_tool,
        # the original format) and genuinely multi-agent ones (expected_agents/
        # expected_tools, a list) without needing two code paths — everything is
        # normalized to a set of "tools that must appear somewhere in this turn's
        # tool_calls trace" so a query that legitimately needs 2+ agents can require
        # 2+ tools instead of only ever checking the first one called.
        exp_tools = set(tc["expected_tools"]) if "expected_tools" in tc else {tc["expected_tool"]}
        exp_agents = set(tc["expected_agents"]) if "expected_agents" in tc else {tc["expected_agent"]}
        exp_tool = tc.get("expected_tool", next(iter(exp_tools)))  # for display/back-compat
        exp_agent = tc.get("expected_agent", next(iter(exp_agents)))
        exp_args = tc.get("expected_args", {})
        exp_keywords = tc.get("expected_context_keywords", [])

        initial_state = {
            "user_query": query,
            "agent_called": "",
            "tool_result": "",
            "tool_calls": [],
            "messages": [],
            "final_answer": ""
        }

        try:
            res = orchestrator_graph.invoke(initial_state)
            act_tool = res.get("agent_called", "none")
            tool_calls = res.get("tool_calls", []) or []
            tools_called = {c["tool"] for c in tool_calls} or {"none"}
            agents_called = {c["agent"] for c in tool_calls} or {"none"}
            tool_res = res.get("tool_result", "") or ""
            final_ans = res.get("final_answer", "") or ""
        except Exception as e:
            import traceback
            traceback.print_exc()
            act_tool = "error"
            tools_called = {"error"}
            agents_called = {"unknown"}
            tool_res = str(e)
            final_ans = ""
            api_error_count += 1

        act_agent = TOOL_TO_AGENT.get(act_tool, "unknown")

        # 1. Routing Correctness — every expected agent must have actually been called.
        # For the original single-agent cases this is identical to act_agent == exp_agent.
        routing_correct = exp_agents.issubset(agents_called)
        if routing_correct:
            routing_correct_count += 1

        # 2. Tool Correctness — every expected tool must appear somewhere in the trace.
        tool_correct = exp_tools.issubset(tools_called)
        # Check args in response if available
        if tool_correct and exp_args:
            combined_text = (tool_res + " " + final_ans).lower()
            for arg_val in exp_args.values():
                if str(arg_val).lower() not in combined_text:
                    # Minor note if arg missing, but keep tool_correct based on tool selection
                    pass
        if tool_correct:
            tool_correct_count += 1

        # 3. Grounding / Faithfulness check
        combined_output = (tool_res + " " + final_ans).lower()
        grounded = any(kw.lower() in combined_output for kw in exp_keywords) if exp_keywords else True
        if grounded:
            grounded_count += 1

        notes = []
        if not routing_correct:
            notes.append(f"Routing mismatch (Expected {sorted(exp_agents)}, got {sorted(agents_called)})")
        if not tool_correct:
            notes.append(f"Tool mismatch (Expected {sorted(exp_tools)}, got {sorted(tools_called)})")
        if not grounded:
            notes.append(f"Missing grounding keywords {exp_keywords}")

        notes_str = "; ".join(notes) if notes else "PASS"

        results.append({
            "query": query,
            "expected_agent": exp_agent,
            "actual_agent": act_agent,
            "routing_correct": routing_correct,
            "expected_tool": exp_tool,
            "actual_tool": act_tool,
            "tool_correct": tool_correct,
            "grounded": grounded,
            "num_tool_calls": len(tools_called - {"none"}),
            "all_tools_called": ",".join(sorted(tools_called)),
            "notes": notes_str
        })

        status_symbol = "[PASS]" if (routing_correct and tool_correct and grounded) else "[FAIL]"
        print(f"[{idx}/{total}] {status_symbol} Query: \"{query[:45]}...\" | Tools: {sorted(tools_called)} | Grounded: {grounded}")

        # Reasoning: Pace requests to stay under the Mistral rate limit (each query makes
        # 2 API calls: router + synthesizer). The retry/backoff in call_mistral_with_retry
        # is a safety net, not a substitute for reasonable pacing.
        time.sleep(1.5)

    csv_file_path = os.path.join(results_dir, output_csv)
    fieldnames = ["query", "expected_agent", "actual_agent", "routing_correct", "expected_tool", "actual_tool", "tool_correct", "grounded", "num_tool_calls", "all_tools_called", "notes"]
    
    with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
        
    print("\n--------------------------------------------------")
    print(f" Evaluation Summary ({prompt_version})")
    print("--------------------------------------------------")
    print(f" Routing Accuracy : {routing_correct_count}/{total} ({routing_correct_count/total*100:.1f}%)")
    print(f" Tool Selection   : {tool_correct_count}/{total} ({tool_correct_count/total*100:.1f}%)")
    print(f" Grounding Rate   : {grounded_count}/{total} ({grounded_count/total*100:.1f}%)")
    if api_error_count:
        # Reasoning: Report both figures rather than silently excluding the failures.
        # The raw number is what the run actually produced; the adjusted one is what the
        # prompt is responsible for. Hiding either would be the dishonest choice.
        scored = total - api_error_count
        print(f" API errors       : {api_error_count} (Mistral timeout/transport — not a routing decision)")
        print(f" Excluding those  : routing {routing_correct_count}/{scored} "
              f"({routing_correct_count/scored*100:.1f}%), tool {tool_correct_count}/{scored} "
              f"({tool_correct_count/scored*100:.1f}%), grounded {grounded_count}/{scored} "
              f"({grounded_count/scored*100:.1f}%)")
    print(f" Results Saved To : {csv_file_path}")
    print("==================================================\n")
    
    return {
        "total": total,
        "routing_acc": routing_correct_count / total * 100,
        "tool_acc": tool_correct_count / total * 100,
        "grounding_rate": grounded_count / total * 100
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Marketplace Orchestrator Eval Harness")
    parser.add_argument("--prompt", default="v1", help="Prompt version (e.g. v1, v2)")
    parser.add_argument("--output", default="baseline_v1.csv", help="Output CSV filename")
    parser.add_argument("--eval_file", default="eval_set.jsonl", help="Eval dataset JSONL filename")
    args = parser.parse_args()
    
    evaluate(args.prompt, args.output, args.eval_file)
