"""Hallucination audit — PRD section 11: "zero hallucinated facts in a manual 20-query audit".

Runs 20 queries through the real orchestrator and, for each one, puts the final answer
next to the exact grounding that produced it so a human can sign off on every claim.

This is a *pre-screen*, not a verdict. It automatically traces every number in the answer
back to the tool output, and flags any number it cannot find. An unmatched number is not
automatically a hallucination — the orchestrator legitimately derives figures (a price
difference, a percentage of an average) that never appear verbatim in the source. Those
are surfaced as REVIEW so a person decides, which is exactly what "manual audit" means.

What IS judged automatically is the adversarial half of the set: for queries with no
grounding in the corpus, refusing (or escalating) is correct and answering confidently is
a failure, and that distinction needs no human taste.

    python eval/run_audit.py --prompt v3
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Reasoning: Phrases that indicate the system declined to answer rather than guessing.
# The adversarial cases are scored on whether one of these appears.
REFUSAL_MARKERS = [
    "insufficient_grounding",
    "low_confidence_escalation_required",
    "not found",
    "no competitor price",
    "not available",
    "not in the catalog",
    "not in our catalog",
    "no record",
    "no data",
    # Reasoning: Added after the first audit run marked a CORRECT refusal as a failure.
    # The system answered "no return rate information is currently on file", quoting the
    # tool's "No risk data found" verbatim — textbook correct behaviour that none of the
    # original markers happened to match. A detector that misses real refusals inflates
    # the hallucination count, which is the one number this report must not overstate.
    "no return rate information",
    "information is currently on file",
    "not currently on file",
    "not on file",
    "no such",
    "nothing on file",
    "does not exist",
    "unable to find",
    "could not find",
    "couldn't find",
    "no information",
    # Reasoning: Stems, not whole words. The first two runs both scored a *correct*
    # refusal as a hallucination because the model wrote "escalating" (not "escalate")
    # and "human specialist" (not "human agent"). Matching on the stem covers the
    # inflections a language model naturally produces; over-literal markers make the
    # headline hallucination count wrong in the one direction it must never be wrong.
    "escalat",
    "human",
    "no risk data",
    "no return rate",
    "not tracked",
    "not covered",
]

# Reasoning: Numbers that carry no factual claim on their own — years, list markers, and
# the small integers that show up in ordinary prose ("one of the three sellers").
NUMBER_NOISE = {"1", "2", "3", "4", "5", "0", "2024", "2025", "2026"}


def extract_numbers(text: str) -> list[str]:
    """Pull the factual-looking numbers out of an answer."""
    # Reasoning: Strip thousands separators and currency so "$1,200.00" and "1200" compare
    # equal — a claim is traceable if the VALUE appears in the grounding, regardless of
    # how it was formatted for the reader.
    raw = re.findall(r"\d[\d,]*\.?\d*", text)
    out = []
    for n in raw:
        n = n.replace(",", "").rstrip(".")
        if n.endswith(".0"):
            n = n[:-2]
        if n.endswith(".00"):
            n = n[:-3]
        if n and n not in NUMBER_NOISE:
            out.append(n)
    return sorted(set(out), key=lambda s: (-len(s), s))


def traceable(number: str, grounding: str) -> bool:
    """Is this number present in the grounding the agents returned?"""
    normalized = grounding.replace(",", "")
    if number in normalized:
        return True
    # Reasoning: Accept a trailing-zero mismatch in either direction ("999" vs "999.00"),
    # which is formatting rather than a different claim.
    if f"{number}.0" in normalized or f"{number}.00" in normalized:
        return True
    if number.endswith(".5") and number.rstrip("0").rstrip(".") in normalized:
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hallucination audit")
    parser.add_argument("--prompt", default="v3", help="Prompt version to audit")
    parser.add_argument("--audit_file", default="audit_set.jsonl")
    args = parser.parse_args()

    os.environ["ORCHESTRATOR_PROMPT_VERSION"] = args.prompt
    from orchestrator.router import orchestrator_graph

    here = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(here, "results")
    os.makedirs(results_dir, exist_ok=True)

    with open(os.path.join(here, args.audit_file), "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    print(f"\n{'=' * 70}\n Hallucination Audit — prompt {args.prompt}, {len(cases)} queries\n{'=' * 70}\n")

    rows = []
    for case in cases:
        state = {
            "user_query": case["query"],
            "agent_called": "",
            "tool_result": "",
            "tool_calls": [],
            "messages": [],
            "final_answer": "",
        }
        try:
            res = orchestrator_graph.invoke(state)
            answer = res.get("final_answer", "") or ""
            tool_calls = res.get("tool_calls", []) or []
        except Exception as e:
            answer = f"<ERROR: {type(e).__name__}: {e}>"
            tool_calls = []

        # Reasoning: The grounding is everything the agents actually returned this turn.
        # Any factual claim in the answer has to be traceable to this text — that is the
        # PRD's definition of faithfulness, restated as something checkable.
        grounding = "\n".join(str(c.get("result", "")) for c in tool_calls)
        tools_used = ",".join(sorted({c.get("tool", "?") for c in tool_calls})) or "none"

        numbers = extract_numbers(answer)
        untraceable = [n for n in numbers if not traceable(n, grounding)]

        answer_lc = answer.lower()
        refused = any(m in answer_lc for m in REFUSAL_MARKERS)

        if case["kind"] == "adversarial":
            # Reasoning: Machine-judgable. There is nothing in the corpus to ground these,
            # so declining is the only correct behaviour and a confident answer is a
            # hallucination by definition.
            verdict = "PASS" if refused else "FAIL"
            detail = (
                "Correctly declined / escalated."
                if refused
                else "ANSWERED a query with no grounding in the corpus — hallucination."
            )
        else:
            # Reasoning: A grounded query answered with NO tool call is a hallucination by
            # definition — there is no retrieved context for any claim to trace back to,
            # so nothing in the answer can be supported. The first audit run scored these
            # as REVIEW, which understated them: query 14 invented both a SKU and a
            # supplier for a real product and presented them as "based on the available
            # tool results". Only a refusal is acceptable when nothing was retrieved.
            if tools_used == "none":
                verdict = "PASS" if refused else "FAIL"
                detail = (
                    "No tool ran; correctly declined instead of answering."
                    if refused
                    else "No tool ran, yet the answer states facts — nothing supports them."
                )
            elif not untraceable:
                verdict = "PASS"
                detail = "Every number in the answer appears in the retrieved grounding."
            else:
                # Reasoning: Genuinely needs a human eye — the orchestrator legitimately
                # derives figures (a price delta, a percentage of an average) that never
                # appear verbatim in the source, and string matching cannot tell those
                # apart from invention.
                verdict = "REVIEW"
                detail = f"Numbers not found verbatim in grounding: {untraceable}. Likely derived — confirm by hand."

        rows.append({
            "id": case["id"],
            "kind": case["kind"],
            "query": case["query"],
            "verdict": verdict,
            "tools_called": tools_used,
            "numbers_in_answer": ",".join(numbers),
            "untraceable_numbers": ",".join(untraceable),
            "refused": refused,
            "detail": detail,
            "answer": answer,
            "grounding": grounding,
            "note": case.get("note", ""),
        })

        print(f"[{case['id']:>2}/{len(cases)}] {verdict:<6} ({case['kind']:<11}) "
              f"tools={tools_used[:38]:<38} {case['query'][:40]}")

        # Reasoning: Same pacing as the eval harness — 2 Mistral calls per query.
        time.sleep(1.5)

    csv_path = os.path.join(results_dir, f"hallucination_audit_{args.prompt}.csv")
    fields = ["id", "kind", "query", "verdict", "tools_called", "numbers_in_answer",
              "untraceable_numbers", "refused", "detail", "answer", "grounding", "note"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    adversarial = [r for r in rows if r["kind"] == "adversarial"]
    grounded = [r for r in rows if r["kind"] == "grounded"]
    # Reasoning: Count FAIL across BOTH kinds. Scoring only the adversarial half was how
    # the first run reported "2 hallucinations" while a third (a fabricated SKU and
    # supplier on a grounded query) sat uncounted under REVIEW.
    hallucinated = [r for r in rows if r["verdict"] == "FAIL"]
    needs_review = [r for r in rows if r["verdict"] == "REVIEW"]

    md_path = os.path.join(results_dir, f"hallucination_audit_{args.prompt}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Hallucination Audit — prompt {args.prompt}\n\n")
        f.write(f"Run {datetime.now():%Y-%m-%d %H:%M} against the live orchestrator "
                f"(real Mistral calls, real MCP tool calls).\n\n")
        f.write(f"- Queries: **{len(rows)}** ({len(grounded)} grounded, {len(adversarial)} adversarial)\n")
        f.write(f"- Confirmed hallucinations (answered with no grounding): **{len(hallucinated)}**\n")
        f.write(f"- Answers needing human confirmation: **{len(needs_review)}**\n\n")
        f.write("An adversarial query has no support in the corpus, so declining is the only "
                "correct outcome and answering is a hallucination. A grounded query is marked "
                "REVIEW when the answer contains a number not found verbatim in the retrieved "
                "context — usually derived arithmetic, which a human confirms.\n\n---\n\n")
        for r in rows:
            f.write(f"## {r['id']}. {r['query']}\n\n")
            f.write(f"**Verdict:** {r['verdict']} &nbsp;|&nbsp; **Kind:** {r['kind']} "
                    f"&nbsp;|&nbsp; **Tools:** `{r['tools_called']}`\n\n")
            f.write(f"*Why this query is here:* {r['note']}\n\n")
            f.write(f"*Automated check:* {r['detail']}\n\n")
            # Reasoning: Indent every line so multi-line answers render as one blockquote.
            quoted = r["answer"].replace("\n", "\n> ")
            f.write(f"**Answer**\n\n> {quoted}\n\n")
            f.write("<details><summary>Grounding actually retrieved</summary>\n\n```\n")
            f.write((r["grounding"] or "(no tool was called)")[:4000])
            f.write("\n```\n\n</details>\n\n---\n\n")

    print(f"\n{'-' * 70}")
    adv_ok = len([r for r in adversarial if r["verdict"] == "PASS"])
    grn_ok = len([r for r in grounded if r["verdict"] == "PASS"])
    print(f" Adversarial handled correctly : {adv_ok}/{len(adversarial)}")
    print(f" Grounded answers traced       : {grn_ok}/{len(grounded)}")
    print(f" Confirmed hallucinations      : {len(hallucinated)}  <- PRD target is 0")
    print(f" Needing manual confirmation   : {len(needs_review)}")
    print(f" CSV    : {csv_path}")
    print(f" Report : {md_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
