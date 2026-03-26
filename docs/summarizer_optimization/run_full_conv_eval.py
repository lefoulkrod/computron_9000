#!/usr/bin/env python3
"""Evaluate compaction quality on full-fidelity conversations.

Unlike run_real_eval.py which tests summarizer output on already-compacted
records, this runner tests the full compaction pipeline: boundary logic
(keep_recent_groups) + serialization + summarization. It simulates what
would happen if these conversations had triggered compaction.

Usage:
    # Run compaction simulation on all full conversations:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py

    # Skip LLM judge (just show summaries):
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py --skip-judge

    # Test a specific conversation:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py --conv 3ad4d39b

    # Save results:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py --save
"""

import argparse
import asyncio
import copy
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sdk.context._strategy import (
    SummarizeStrategy,
    _CLEARED_TOOL_RESULT,
    _ARG_CLEAR_CAP,
    _SUMMARY_PREFIX,
    _count_kept_by_assistant_groups,
    _has_following_assistant_roles,
    _serialize_messages,
)
from sdk.providers import get_provider

_CONVS_DIR = Path(__file__).resolve().parent / "full_conversations"
_ANNOTATIONS_FILE = _CONVS_DIR / "annotations.json"
_JUDGE_MODEL = "kimi-k2.5:cloud"

_JUDGE_PROMPT = """You are evaluating the quality of a conversation summary. You will see:
1. The original conversation messages (serialized)
2. The summary that was produced

Score the summary on these criteria (1-5 each):

**Fact Retention**: Does the summary preserve the key facts, data, URLs, prices, \
names, and findings? (5 = all important facts preserved, 1 = most facts lost or \
hallucinated)

**Current State**: Does the summary accurately describe what was happening at the \
end of the conversation? (5 = accurate and actionable, 1 = wrong or vague)

**Process Suppression**: Does the summary focus on RESULTS and avoid narrating \
steps taken? (5 = pure facts, 1 = reads like a click log)

**Hallucination**: Does the summary contain any facts NOT present in the input? \
(5 = no hallucinations, 1 = significant fabricated content)

Output ONLY valid JSON:
{"fact_retention": N, "current_state": N, \
"process_suppression": N, "hallucination": N, "issues": "brief notes"}"""


def check_must_contain(summary: str, patterns: list[str]) -> tuple[int, int]:
    """Check required fact patterns. Returns (passed, total)."""
    passed = 0
    for pattern in patterns:
        if re.search(pattern, summary, re.IGNORECASE):
            passed += 1
    return passed, len(patterns)


async def judge_summary(provider, serialized: str, summary: str, msg_count: int) -> dict:
    """Score a summary using the LLM judge."""
    if len(serialized) > 30_000:
        serialized = serialized[:15_000] + "\n\n...[truncated]...\n\n" + serialized[-15_000:]

    user_content = (
        f"## CONVERSATION ({msg_count} messages)\n\n"
        f"{serialized}\n\n---\n\n"
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


async def evaluate_conversation(
    provider,
    conv_id: str,
    messages: list[dict],
    annotation: dict,
    skip_judge: bool = False,
) -> dict:
    """Simulate compaction on a full conversation and evaluate the result."""
    # Strip system messages
    non_system = [m for m in messages if m.get("role") != "system"]

    # Apply the same boundary logic as production
    # Pin first user message
    pin_offset = 0
    for m in non_system:
        if m.get("role") == "user":
            pin_offset = 1
            break

    body = non_system[pin_offset:]
    keep_count = _count_kept_by_assistant_groups(body, keep_groups=2)

    if keep_count >= len(body):
        compactable = body
        kept = []
    else:
        compactable = body[:-keep_count] if keep_count > 0 else body
        kept = body[-keep_count:] if keep_count > 0 else []

    result = {
        "conv_id": conv_id,
        "conversation_type": annotation.get("conversation_type", "unknown"),
        "total_messages": len(non_system),
        "compactable_messages": len(compactable),
        "kept_messages": len(kept),
    }

    # Simulate tool clearing on compactable messages (same as production).
    compactable = copy.deepcopy(compactable)
    roles = [m.get("role", "") for m in compactable]
    for i, m in enumerate(compactable):
        if roles[i] == "tool":
            content = m.get("content") or ""
            if (
                len(content) > len(_CLEARED_TOOL_RESULT)
                and _has_following_assistant_roles(roles, i, len(compactable))
            ):
                m["content"] = _CLEARED_TOOL_RESULT
        elif roles[i] == "assistant" and _has_following_assistant_roles(
            roles, i, len(compactable),
        ):
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or tc
                args = fn.get("arguments")
                if not isinstance(args, dict):
                    continue
                for key, val in args.items():
                    val_str = str(val)
                    if len(val_str) > _ARG_CLEAR_CAP:
                        args[key] = val_str[:_ARG_CLEAR_CAP] + f"... [{len(val_str):,} chars]"

    # Serialize and summarize the compactable window
    serialized = _serialize_messages(copy.deepcopy(compactable))
    result["serialized_chars"] = len(serialized)

    strategy = SummarizeStrategy()
    start = time.perf_counter()
    summary, model = await strategy._summarize(copy.deepcopy(compactable))
    elapsed = time.perf_counter() - start

    result["model"] = model
    result["summary_chars"] = len(summary)
    result["time"] = round(elapsed, 1)
    result["summary"] = summary

    # Deterministic checks
    mc_passed, mc_total = check_must_contain(
        summary, annotation.get("must_contain", []),
    )
    result["facts_found"] = mc_passed
    result["facts_total"] = mc_total

    # LLM judge
    if not skip_judge:
        try:
            scores = await judge_summary(
                provider, serialized, summary, len(compactable),
            )
            if "error" not in scores:
                result.update(scores)
            else:
                result["judge_error"] = scores["error"]
        except Exception as e:
            result["judge_error"] = str(e)[:100]

    return result


def print_result(result: dict) -> None:
    """Print evaluation result for a single conversation."""
    print(f"\n{'='*70}")
    print(f"Conversation: {result['conv_id']}  ({result['conversation_type']})")
    print(f"Messages: {result['total_messages']}  "
          f"Compacted: {result['compactable_messages']}  "
          f"Kept: {result['kept_messages']}")
    print(f"Serialized: {result['serialized_chars']:,} chars  "
          f"Summary: {result['summary_chars']:,} chars  "
          f"Time: {result['time']}s")
    print(f"Facts: {result['facts_found']}/{result['facts_total']}")

    if "fact_retention" in result:
        print(f"Judge: F={result['fact_retention']} "
              f"S={result['current_state']} "
              f"P={result['process_suppression']} "
              f"H={result['hallucination']}")
        if result.get("issues"):
            print(f"Issues: {result['issues'][:150]}")

    if result.get("judge_error"):
        print(f"Judge ERROR: {result['judge_error'][:80]}")

    print(f"\n--- Summary ---")
    print(result.get("summary", "")[:2000])
    if len(result.get("summary", "")) > 2000:
        print("... [truncated]")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate compaction quality on full conversations",
    )
    parser.add_argument(
        "--conv", type=str, default=None,
        help="Filter to a specific conversation ID prefix",
    )
    parser.add_argument(
        "--skip-judge", action="store_true",
        help="Skip LLM judge scoring",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save results to a timestamped file",
    )
    args = parser.parse_args()

    # Load annotations
    annotations = json.loads(_ANNOTATIONS_FILE.read_text())["records"]

    # Load conversations
    records: list[tuple[str, list[dict], dict]] = []
    for f in sorted(_CONVS_DIR.glob("*.json")):
        if f.name == "annotations.json":
            continue
        conv_id = f.stem
        if args.conv and not conv_id.startswith(args.conv):
            continue
        data = json.loads(f.read_text())
        messages = data.get("input_messages", [])
        ann = annotations.get(conv_id, {})
        records.append((conv_id, messages, ann))

    provider = get_provider() if not args.skip_judge else None

    print(f"Conversations: {len(records)}")
    print()

    results = []
    for conv_id, messages, annotation in records:
        result = await evaluate_conversation(
            provider, conv_id, messages, annotation,
            skip_judge=args.skip_judge,
        )
        results.append(result)
        print_result(result)

    # Aggregate
    if len(results) > 1:
        print(f"\n{'='*70}")
        print("AGGREGATE")
        judged = [r for r in results if "fact_retention" in r]
        if judged:
            for key in ["fact_retention", "current_state", "process_suppression", "hallucination"]:
                vals = [r[key] for r in judged]
                print(f"  {key}: {sum(vals)/len(vals):.2f}")
        facts_found = sum(r.get("facts_found", 0) for r in results)
        facts_total = sum(r.get("facts_total", 0) for r in results)
        if facts_total:
            print(f"  facts: {facts_found}/{facts_total} ({facts_found/facts_total:.0%})")

    if args.save:
        runs_dir = Path(__file__).resolve().parent / "runs"
        runs_dir.mkdir(exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = runs_dir / f"full_conv_eval_{ts}.json"
        for r in results:
            r.pop("summary", None)
        save_path.write_text(json.dumps(results, indent=2))
        print(f"\nSaved to: {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
