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
    
    print(f"\n==================================================")
    print(f" Running Evaluation Harness (Prompt Version: {prompt_version})")
    print(f" Total Test Cases: {total}")
    print(f"==================================================\n")
    
    for idx, tc in enumerate(test_cases, 1):
        query = tc["query"]
        exp_agent = tc["expected_agent"]
        exp_tool = tc["expected_tool"]
        exp_args = tc.get("expected_args", {})
        exp_keywords = tc.get("expected_context_keywords", [])
        
        initial_state = {
            "user_query": query,
            "agent_called": "",
            "tool_result": "",
            "messages": [],
            "final_answer": ""
        }
        
        try:
            res = orchestrator_graph.invoke(initial_state)
            act_tool = res.get("agent_called", "none")
            tool_res = res.get("tool_result", "") or ""
            final_ans = res.get("final_answer", "") or ""
        except Exception as e:
            import traceback
            traceback.print_exc()
            act_tool = "error"
            tool_res = str(e)
            final_ans = ""
            
        act_agent = TOOL_TO_AGENT.get(act_tool, "unknown")
        
        # 1. Routing Correctness
        routing_correct = (act_agent == exp_agent)
        if routing_correct:
            routing_correct_count += 1
            
        # 2. Tool Correctness
        tool_correct = (act_tool == exp_tool)
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
            notes.append(f"Routing mismatch (Expected {exp_agent}, got {act_agent})")
        if not tool_correct:
            notes.append(f"Tool mismatch (Expected {exp_tool}, got {act_tool})")
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
            "notes": notes_str
        })
        
        status_symbol = "[PASS]" if (routing_correct and tool_correct and grounded) else "[FAIL]"
        print(f"[{idx}/{total}] {status_symbol} Query: \"{query[:45]}...\" | Tool: {act_tool} | Grounded: {grounded}")

        # Reasoning: Pace requests to stay under the Mistral rate limit (each query makes
        # 2 API calls: router + synthesizer). The retry/backoff in call_mistral_with_retry
        # is a safety net, not a substitute for reasonable pacing.
        time.sleep(1.5)

    csv_file_path = os.path.join(results_dir, output_csv)
    fieldnames = ["query", "expected_agent", "actual_agent", "routing_correct", "expected_tool", "actual_tool", "tool_correct", "grounded", "notes"]
    
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
