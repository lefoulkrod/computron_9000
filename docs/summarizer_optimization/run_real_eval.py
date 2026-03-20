#!/usr/bin/env python3
"""Evaluate summarizer quality on real compaction records.

Combines deterministic checks (remaining work, required facts, section structure)
with LLM-as-judge scoring (fact retention, remaining work accuracy, current state,
process suppression).

Usage:
    # Evaluate the stored production summaries (baseline):
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py

    # Re-run the summarizer and evaluate new output:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --rerun

    # Save results to a file:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --save
"""

import argparse
import asyncio
import copy
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sdk.context._strategy import SummarizeStrategy, _SUMMARY_PREFIX
from sdk.providers import get_provider

_RECORDS_DIR = Path(__file__).resolve().parent / "real_compactions"
_ANNOTATIONS_FILE = _RECORDS_DIR / "annotations.json"
_BASELINE_FILE = _RECORDS_DIR / "baseline_scores.json"
_JUDGE_MODEL = "kimi-k2.5:cloud"

_REQUIRED_SECTIONS = [
    "## Completed Work",
    "## Key Data",
    "## Current State",
]

_JUDGE_PROMPT = """You are evaluating the quality of a conversation summary. You will see:
1. The original conversation messages (serialized)
2. The summary that was produced

NOTE: The input messages may contain a PRIOR SUMMARY from an earlier compaction \
(marked with "[PRIOR SUMMARY]"). Facts from the prior summary are legitimate \
source data — they are NOT hallucinations.

Score the summary on these criteria (1-5 each):

**Fact Retention**: Does the summary preserve the key facts, data, URLs, prices, \
names, and findings? (5 = all important facts preserved, 1 = most facts lost or \
hallucinated)

**Current State**: Does the summary accurately describe what was happening at the \
end of the conversation? What the assistant was doing, what the user last asked for, \
any in-progress work? An agent reading this should know exactly what to do next. \
(5 = accurate and actionable, 1 = wrong, missing, or vague)

**Process Suppression**: Does the summary focus on RESULTS and avoid narrating \
steps taken (clicked X, scrolled, tried Y)? (5 = pure facts, 1 = reads like a \
click log)

Output ONLY valid JSON in this exact format:
{"fact_retention": N, "current_state": N, \
"process_suppression": N, "issues": "brief description of problems"}"""


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

def check_sections(summary: str) -> bool:
    """Check that all 4 required sections are present."""
    return all(section in summary for section in _REQUIRED_SECTIONS)


def check_remaining_work(summary: str, task_complete: bool) -> bool:
    """Check if Remaining Work correctly says None or not."""
    rm = re.search(r"## Remaining Work\s*\n(.*?)(?:\n##|\Z)", summary, re.DOTALL)
    if not rm:
        return False
    text = rm.group(1).strip()
    has_none = bool(re.search(r"\bNone\b", text, re.IGNORECASE))
    return has_none == task_complete


def check_must_contain(summary: str, patterns: list[str]) -> tuple[int, int]:
    """Check required fact patterns. Returns (passed, total)."""
    passed = 0
    for pattern in patterns:
        if re.search(pattern, summary, re.IGNORECASE):
            passed += 1
    return passed, len(patterns)


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

def _serialize_for_judge(record: dict) -> str:
    """Serialize input messages for the judge (truncated for context)."""
    msgs = record["input_messages"]
    parts = []
    for m in msgs:
        role = m.get("role", "?")
        content = (m.get("content") or "")[:500]
        if content.startswith(_SUMMARY_PREFIX):
            parts.append(f"[PRIOR SUMMARY]: {content[len(_SUMMARY_PREFIX):]}")
        elif role == "assistant":
            tc = m.get("tool_calls")
            if tc:
                names = [t.get("function", {}).get("name", "?") for t in tc]
                if content:
                    parts.append(
                        f"Assistant: {content}\n  [tools: {', '.join(names)}]",
                    )
                else:
                    parts.append(f"Assistant: [tools: {', '.join(names)}]")
            elif content:
                parts.append(f"Assistant: {content}")
        elif role == "tool":
            tn = m.get("tool_name", "?")
            parts.append(f"Tool({tn}): {content[:200]}")
        elif role == "user":
            parts.append(f"User: {content}")

    text = "\n\n".join(parts)
    if len(text) > 30_000:
        text = text[:15_000] + "\n\n...[truncated]...\n\n" + text[-15_000:]
    return text


async def judge_summary(provider, record: dict, summary: str) -> dict:
    """Score a summary using the LLM judge."""
    conv_text = _serialize_for_judge(record)
    user_content = (
        f"## CONVERSATION ({record['messages_compacted']} messages)\n\n"
        f"{conv_text}\n\n---\n\n"
        f"## SUMMARY PRODUCED\n\n{summary}"
    )

    response = await asyncio.wait_for(
        provider.chat(
            model=_JUDGE_MODEL,
            messages=[
                {"role": "system", "content": _JUDGE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            think=False,
            options={"temperature": 0, "num_ctx": 65536},
        ),
        timeout=120,
    )

    text = response.message.content or ""
    m = re.search(r"\{[^}]+\}", text, re.DOTALL)
    if m:
        return json.loads(m.group())
    return {"error": text[:200]}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def evaluate_record(
    provider,
    rid: str,
    record: dict,
    annotation: dict,
    summary: str,
) -> dict:
    """Evaluate a single summary against deterministic checks + LLM judge."""
    result = {"rid": rid}

    # Deterministic checks
    result["has_sections"] = check_sections(summary)
    result["remaining_work_correct"] = check_remaining_work(
        summary, annotation.get("task_complete", False),
    )
    mc_passed, mc_total = check_must_contain(
        summary, annotation.get("must_contain", []),
    )
    result["facts_found"] = mc_passed
    result["facts_total"] = mc_total

    # LLM judge
    try:
        scores = await judge_summary(provider, record, summary)
        if "error" not in scores:
            result.update(scores)
        else:
            result["judge_error"] = scores["error"]
    except Exception as e:
        result["judge_error"] = str(e)[:100]

    return result


def _compute_scores(results: list[dict]) -> dict:
    """Compute aggregate scores from a list of per-record results."""
    n = len(results)
    rw_correct = sum(1 for r in results if r.get("remaining_work_correct"))
    sec_correct = sum(1 for r in results if r.get("has_sections"))
    facts_found = sum(r.get("facts_found", 0) for r in results)
    facts_total = sum(r.get("facts_total", 0) for r in results)

    judged = [r for r in results if "fact_retention" in r]
    judge_avgs = {}
    for key in ["fact_retention", "current_state", "process_suppression"]:
        vals = [r[key] for r in judged]
        judge_avgs[key] = sum(vals) / len(vals) if vals else 0

    return {
        "n": n,
        "remaining_work_pct": rw_correct / n if n else 0,
        "sections_pct": sec_correct / n if n else 0,
        "facts_pct": facts_found / facts_total if facts_total else 1,
        **judge_avgs,
    }


def _print_scores(label: str, scores: dict) -> None:
    """Print a scores summary block."""
    print(f"{label}:")
    print(f"  Remaining work correct: {scores['remaining_work_pct']:.0%}")
    print(f"  Has all sections:       {scores['sections_pct']:.0%}")
    print(f"  Required facts found:   {scores['facts_pct']:.0%}")
    print(f"  Judge — fact: {scores['fact_retention']:.2f}  state: {scores['current_state']:.2f}  process: {scores['process_suppression']:.2f}")


def _print_comparison(baseline: dict, current: dict) -> None:
    """Print a side-by-side comparison with deltas."""
    print("Comparison (current vs baseline):")
    rows = [
        ("Required facts found", "facts_pct", True),
        ("Judge: fact retention", "fact_retention", True),
        ("Judge: current state", "current_state", True),
        ("Judge: process suppression", "process_suppression", True),
    ]
    for label, key, higher_is_better in rows:
        b = baseline[key]
        c = current[key]
        delta = c - b
        if key.endswith("_pct"):
            arrow = "▲" if delta > 0 else "▼" if delta < 0 else "="
            print(f"  {label:<28} {b:.0%} → {c:.0%}  {arrow} {abs(delta):.0%}")
        else:
            arrow = "▲" if delta > 0 else "▼" if delta < 0 else "="
            print(f"  {label:<28} {b:.2f} → {c:.2f}  {arrow} {abs(delta):.2f}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate summarizer on real data")
    parser.add_argument(
        "--rerun", action="store_true",
        help="Re-run the summarizer instead of evaluating stored summaries",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save results to a timestamped file",
    )
    args = parser.parse_args()

    # Load annotations
    annotations = json.loads(_ANNOTATIONS_FILE.read_text())["records"]

    # Load records
    records: list[tuple[str, dict, dict]] = []
    for f in sorted(_RECORDS_DIR.glob("*.json")):
        if f.name in ("annotations.json", "baseline_scores.json"):
            continue
        r = json.loads(f.read_text())
        rid = f.stem[:8]
        ann = annotations.get(rid, {})
        records.append((rid, r, ann))

    provider = get_provider()
    strategy = SummarizeStrategy()

    print(f"Records: {len(records)}")
    print(f"Mode: {'re-run summarizer' if args.rerun else 'evaluate stored summaries'}")
    print()

    results = []
    for rid, record, annotation in records:
        if args.rerun:
            msgs = copy.deepcopy(record["input_messages"])
            prior = record.get("prior_summary")
            start = time.perf_counter()
            summary, _ = await strategy._summarize(msgs, prior)
            elapsed = time.perf_counter() - start
        else:
            summary = record["summary_text"]
            elapsed = 0

        result = await evaluate_record(provider, rid, record, annotation, summary)
        result["summary_chars"] = len(summary)
        result["time"] = round(elapsed, 1)
        results.append(result)

        # Print per-record result
        sec = "✓" if result["has_sections"] else "✗"
        facts = f"{result['facts_found']}/{result['facts_total']}"
        judge = ""
        if "fact_retention" in result:
            judge = (
                f"F={result['fact_retention']} "
                f"S={result['current_state']} P={result['process_suppression']}"
            )
        else:
            judge = f"ERROR: {result.get('judge_error', '?')[:40]}"
        print(f"  {rid}  sec={sec} facts={facts:<5} {judge}")

    # Compute current scores
    current = _compute_scores(results)

    # Load baseline for comparison
    baseline = None
    if _BASELINE_FILE.exists():
        baseline_results = json.loads(_BASELINE_FILE.read_text())
        baseline = _compute_scores(baseline_results)

    # Print summary with comparison
    print(f"\n{'='*70}")
    _print_scores("Current", current)
    if baseline and args.rerun:
        print()
        _print_scores("Baseline", baseline)
        print()
        _print_comparison(baseline, current)

    # Save
    if args.save:
        runs_dir = Path(__file__).resolve().parent / "runs"
        runs_dir.mkdir(exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "rerun" if args.rerun else "baseline"
        save_path = runs_dir / f"real_eval_{mode}_{ts}.json"
        save_path.write_text(json.dumps(results, indent=2))
        print(f"\nSaved to: {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
