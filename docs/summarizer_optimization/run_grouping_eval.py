#!/usr/bin/env python3
"""Evaluate the impact of message grouping on compaction quality.

Replays saved conversation histories up to the first compaction point,
testing different keep_recent_groups values. For each configuration,
computes the compactable window using message group boundaries (never
splitting a tool call from its result), runs the summarizer, and
compares output quality via LLM-as-judge.

A "message group" is one of:
  - A user message (standalone)
  - An assistant message with tool_calls + its corresponding tool result(s)
  - A standalone assistant text message (no tool calls)

Usage:
    # Dry run — show grouping boundaries without calling summarizer:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_grouping_eval.py --dry-run

    # Compare keep_recent_groups=2,3,4 (default):
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_grouping_eval.py

    # Custom group counts:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_grouping_eval.py --groups 2 3 4 6

    # Test on a specific conversation:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_grouping_eval.py --conv 803db597
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

from sdk.context._strategy import SummarizeStrategy, _SUMMARY_PREFIX, _serialize_messages
from sdk.providers import get_provider

_HISTORIES_DIR = Path(os.path.expanduser("~/.computron_9000/conversations"))
_RECORDS_DIR = Path(os.path.expanduser("~/.computron_9000/conversations/summaries"))
_JUDGE_MODEL = "kimi-k2.5:cloud"

# Approximate tokens per character for estimation.
_CHARS_PER_TOKEN = 4

# Default context limit and compaction threshold.
_DEFAULT_CONTEXT_LIMIT = 60_000
_DEFAULT_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Message grouping
# ---------------------------------------------------------------------------


def identify_message_groups(messages: list[dict]) -> list[list[dict]]:
    """Split a flat message list into logical message groups.

    A message group is one of:
      - A user message (alone)
      - An assistant message with tool_calls + all following tool result messages
      - A standalone assistant text message (no tool calls)
      - A standalone tool message (orphaned, shouldn't happen but handle it)

    Returns a list of groups, each group being a list of messages.
    """
    groups: list[list[dict]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "")

        if role == "user":
            groups.append([msg])
            i += 1

        elif role == "assistant":
            tc = msg.get("tool_calls")
            if tc:
                # Collect this assistant message + all following tool results
                group = [msg]
                num_calls = len(tc)
                j = i + 1
                tools_found = 0
                while j < len(messages) and tools_found < num_calls:
                    if messages[j].get("role") == "tool":
                        group.append(messages[j])
                        tools_found += 1
                        j += 1
                    else:
                        break
                groups.append(group)
                i = j
            else:
                groups.append([msg])
                i += 1

        elif role == "tool":
            # Orphaned tool result — shouldn't happen but include it
            groups.append([msg])
            i += 1

        else:
            groups.append([msg])
            i += 1

    return groups


def compute_compactable_by_groups(
    messages: list[dict],
    keep_groups: int,
    pinned_first_user: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Compute the compactable window using message groups.

    Args:
        messages: Non-system messages.
        keep_groups: Number of message groups to keep at the end.
        pinned_first_user: Whether to pin the first user message.

    Returns:
        (compactable_messages, kept_messages)
    """
    pin_offset = 0
    if pinned_first_user and messages and messages[0].get("role") == "user":
        content = messages[0].get("content", "")
        if not content.startswith(_SUMMARY_PREFIX):
            pin_offset = 1

    body = messages[pin_offset:]
    groups = identify_message_groups(body)

    if len(groups) <= keep_groups:
        return [], body

    compact_groups = groups[:-keep_groups]
    kept_groups = groups[-keep_groups:]

    compactable = []
    for g in compact_groups:
        compactable.extend(g)

    kept = []
    for g in kept_groups:
        kept.extend(g)

    return compactable, kept


def compute_compactable_by_raw(
    messages: list[dict],
    keep_recent: int,
    pinned_first_user: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Current behavior: compute compactable window by raw message count."""
    pin_offset = 0
    if pinned_first_user and messages and messages[0].get("role") == "user":
        content = messages[0].get("content", "")
        if not content.startswith(_SUMMARY_PREFIX):
            pin_offset = 1

    body = messages[pin_offset:]
    if keep_recent == 0:
        return body, []
    if len(body) <= keep_recent:
        return [], body

    compactable = body[:-keep_recent]
    kept = body[-keep_recent:]
    return compactable, kept


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate from message content."""
    total_chars = 0
    for m in messages:
        total_chars += len(m.get("content") or "")
        # Tool calls have arguments too
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "")
            if isinstance(args, dict):
                total_chars += len(json.dumps(args))
            else:
                total_chars += len(str(args))
    return total_chars // _CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# Find compaction trigger point
# ---------------------------------------------------------------------------


def find_first_compaction_point(
    messages: list[dict],
    context_limit: int,
    threshold: float,
) -> int | None:
    """Find the message index where compaction would first trigger.

    Walks through messages accumulating estimated token count. Returns the
    index at which fill_ratio first exceeds threshold, or None if it never does.
    """
    token_limit = context_limit
    trigger_tokens = int(token_limit * threshold)

    running_tokens = 0
    for i, m in enumerate(messages):
        content_len = len(m.get("content") or "")
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "")
            if isinstance(args, dict):
                content_len += len(json.dumps(args))
            else:
                content_len += len(str(args))
        running_tokens += content_len // _CHARS_PER_TOKEN

        if running_tokens >= trigger_tokens:
            return i

    return None


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------


_JUDGE_PROMPT = """You are evaluating the quality of a conversation summary. You will see:
1. The original conversation messages (serialized)
2. The summary that was produced

Score the summary on these criteria (1-5 each):

**Fact Retention**: Does the summary preserve the key facts, data, URLs, prices, \
names, and findings? (5 = all important facts preserved, 1 = most facts lost or \
hallucinated)

**Current State**: Does the summary accurately describe what was happening at the \
end of the conversation? What the assistant was doing, what the user last asked for? \
(5 = accurate and actionable, 1 = wrong or vague)

**Process Suppression**: Does the summary focus on RESULTS and avoid narrating \
steps taken? (5 = pure facts, 1 = reads like a click log)

**Hallucination**: Does the summary contain any facts NOT present in the input? \
(5 = no hallucinations, 1 = significant fabricated content)

Output ONLY valid JSON:
{"fact_retention": N, "current_state": N, \
"process_suppression": N, "hallucination": N, "issues": "brief notes"}"""


async def judge_summary(provider, compactable: list[dict], summary: str) -> dict:
    """Score a summary using the LLM judge."""
    serialized = _serialize_messages(copy.deepcopy(compactable))
    if len(serialized) > 30_000:
        serialized = serialized[:15_000] + "\n\n...[truncated]...\n\n" + serialized[-15_000:]

    user_content = (
        f"## CONVERSATION ({len(compactable)} messages)\n\n"
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


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def load_first_compaction_records(
    conv_filter: str | None = None,
) -> list[tuple[str, list[dict]]]:
    """Load first-compaction records from summary files.

    For each conversation, finds the earliest compaction record and returns
    its input_messages as the pre-compaction message list. These are the
    messages that were in the compactable window at the time of the first
    compaction — the full original conversation minus pinned user and
    kept-recent messages.
    """
    from collections import defaultdict

    by_conv: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for f in sorted(_RECORDS_DIR.glob("*.json")):
        if f.name in ("annotations.json", "baseline_scores.json"):
            continue
        r = json.loads(f.read_text())
        conv_id = r.get("conversation_id", "")
        if not conv_id:
            continue
        if conv_filter and not conv_id.startswith(conv_filter):
            continue
        by_conv[conv_id].append((r.get("created_at", ""), r))

    results = []
    for conv_id, records in by_conv.items():
        records.sort(key=lambda x: x[0])
        _, first_record = records[0]
        input_msgs = first_record.get("input_messages", [])
        if len(input_msgs) < 10:
            continue
        results.append((conv_id[:16], input_msgs))

    return results


async def run_eval(
    provider,
    conv_id: str,
    messages: list[dict],
    group_counts: list[int],
    context_limit: int,
    threshold: float,
    dry_run: bool = False,
    skip_judge: bool = False,
) -> dict:
    """Run the grouping evaluation on a single conversation.

    The input messages are from a summary record's input_messages field —
    they represent the compactable window at the time of first compaction.
    We test what happens when we apply different keep_recent_groups values
    to this window, simulating keeping more or fewer messages at the tail.
    """
    # Skip the system message if present
    non_system = [m for m in messages if m.get("role") != "system"]

    if len(non_system) < 10:
        return {"conv_id": conv_id[:16], "skipped": "too few messages"}

    total_groups = identify_message_groups(non_system)

    result = {
        "conv_id": conv_id[:16],
        "total_messages": len(non_system),
        "total_groups": len(total_groups),
        "estimated_tokens": estimate_tokens(non_system),
        "configs": {},
    }

    # Test the current raw keep_recent=6 as baseline, plus group-based variants.
    # Note: these messages were ALREADY the compactable window (kept-recent was
    # excluded). We're simulating: "what if we had kept N more groups from the
    # tail of this window instead of compacting all of it?"
    # raw_0 = compact everything (what actually happened in production)
    # raw_6 = keep 6 raw messages at the tail (simulates current behavior
    #         if these messages had been part of a larger window)
    # groups_N = keep N message groups at the tail
    configs: dict[str, tuple[str, int]] = {"actual": ("raw", 0), "raw_6": ("raw", 6)}
    for n in group_counts:
        configs[f"groups_{n}"] = ("groups", n)

    strategy = SummarizeStrategy()

    for label, (mode, count) in configs.items():
        if mode == "raw":
            compactable, kept = compute_compactable_by_raw(
                non_system, count, pinned_first_user=False,
            )
        else:
            compactable, kept = compute_compactable_by_groups(
                non_system, count, pinned_first_user=False,
            )

        # Check for orphaned tool calls at the boundary
        has_orphan = False
        if compactable:
            last = compactable[-1]
            if last.get("role") == "assistant" and last.get("tool_calls"):
                has_orphan = True

        compact_groups = identify_message_groups(compactable)
        kept_groups = identify_message_groups(kept)

        config_result = {
            "compactable_msgs": len(compactable),
            "compactable_groups": len(compact_groups),
            "kept_msgs": len(kept),
            "kept_groups": len(kept_groups),
            "has_orphaned_tool_call": has_orphan,
        }

        if dry_run:
            # Show boundary info
            if compactable:
                last_compact = compactable[-1]
                first_kept = kept[0] if kept else None
                config_result["boundary"] = {
                    "last_compacted_role": last_compact.get("role"),
                    "last_compacted_has_tools": bool(last_compact.get("tool_calls")),
                    "first_kept_role": first_kept.get("role") if first_kept else None,
                }
        elif compactable:
            # Run summarizer
            serialized = _serialize_messages(copy.deepcopy(compactable))
            config_result["serialized_chars"] = len(serialized)

            if len(serialized) < 50:
                config_result["skipped"] = "serialized input too short"
                config_result["summary"] = ""
            else:
                start = time.perf_counter()
                prior = None
                for m in compactable:
                    c = m.get("content", "")
                    if c.startswith(_SUMMARY_PREFIX):
                        prior = c[len(_SUMMARY_PREFIX):]
                        break
                summary, _ = await strategy._summarize(
                    copy.deepcopy(compactable), prior,
                )
                elapsed = time.perf_counter() - start
                config_result["summary_chars"] = len(summary)
                config_result["time"] = round(elapsed, 1)
                config_result["summary"] = summary

                # Judge
                if not skip_judge:
                    try:
                        scores = await judge_summary(provider, compactable, summary)
                        if "error" not in scores:
                            config_result.update(scores)
                        else:
                            config_result["judge_error"] = scores["error"]
                    except Exception as e:
                        config_result["judge_error"] = str(e)[:100]
        else:
            config_result["skipped"] = "nothing to compact"

        result["configs"][label] = config_result

    return result


def print_result(result: dict) -> None:
    """Print evaluation result for a single conversation."""
    print(f"\n{'='*70}")
    print(f"Conversation: {result['conv_id']}")

    if "skipped" in result:
        print(f"  SKIPPED: {result['skipped']}")
        return

    if "total_messages" not in result:
        print(f"  (no data)")
        return

    print(f"Messages: {result['total_messages']}  Groups: {result['total_groups']}  "
          f"Trigger: msg {result.get('trigger_at_message', '?')}  "
          f"Est tokens: {result.get('estimated_tokens', '?'):,}")

    for label, cfg in result.get("configs", {}).items():
        orphan = " ⚠️ ORPHAN" if cfg.get("has_orphaned_tool_call") else ""
        skip = cfg.get("skipped", "")
        print(f"\n  {label}:  compact={cfg['compactable_msgs']} msgs "
              f"({cfg['compactable_groups']} groups)  "
              f"kept={cfg['kept_msgs']} msgs ({cfg['kept_groups']} groups){orphan}")

        if skip:
            print(f"    SKIPPED: {skip}")
            continue

        if "boundary" in cfg:
            b = cfg["boundary"]
            print(f"    Boundary: last_compacted={b['last_compacted_role']}"
                  f"(tools={b['last_compacted_has_tools']}) → "
                  f"first_kept={b['first_kept_role']}")

        if "summary_chars" in cfg:
            print(f"    Summary: {cfg['summary_chars']} chars  Time: {cfg.get('time', '?')}s")

        if "fact_retention" in cfg:
            print(f"    Judge: F={cfg['fact_retention']} S={cfg['current_state']} "
                  f"P={cfg['process_suppression']} H={cfg['hallucination']}")
            if cfg.get("issues"):
                print(f"    Issues: {cfg['issues'][:100]}")

        if cfg.get("judge_error"):
            print(f"    Judge ERROR: {cfg['judge_error'][:80]}")


def print_summary_table(results: list[dict]) -> None:
    """Print aggregate comparison table across all conversations."""
    # Collect scores per config
    config_scores: dict[str, list[dict]] = {}
    for r in results:
        if r.get("skipped"):
            continue
        for label, cfg in r.get("configs", {}).items():
            if label not in config_scores:
                config_scores[label] = []
            if "fact_retention" in cfg:
                config_scores[label].append(cfg)

    if not config_scores:
        return

    print(f"\n{'='*70}")
    print("AGGREGATE COMPARISON")
    print(f"{'Config':<12} {'N':>3} {'Fact':>5} {'State':>6} {'Proc':>5} "
          f"{'Halluc':>6} {'Orphans':>8} {'Chars':>6}")
    print("-" * 60)

    for label in sorted(config_scores.keys()):
        cfgs = config_scores[label]
        n = len(cfgs)
        if n == 0:
            continue
        fact = sum(c["fact_retention"] for c in cfgs) / n
        state = sum(c["current_state"] for c in cfgs) / n
        proc = sum(c["process_suppression"] for c in cfgs) / n
        halluc = sum(c["hallucination"] for c in cfgs) / n
        orphans = sum(1 for c in cfgs if c.get("has_orphaned_tool_call"))
        chars = sum(c.get("summary_chars", 0) for c in cfgs) / n
        print(f"{label:<12} {n:>3} {fact:>5.2f} {state:>6.2f} {proc:>5.2f} "
              f"{halluc:>6.2f} {orphans:>8} {chars:>6.0f}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate message grouping impact")
    parser.add_argument(
        "--groups", nargs="+", type=int, default=[2, 3, 4],
        help="keep_recent_groups values to test (default: 2 3 4)",
    )
    parser.add_argument(
        "--conv", type=str, default=None,
        help="Filter to a specific conversation ID prefix",
    )
    parser.add_argument(
        "--context-limit", type=int, default=_DEFAULT_CONTEXT_LIMIT,
        help=f"Context limit in tokens (default: {_DEFAULT_CONTEXT_LIMIT})",
    )
    parser.add_argument(
        "--threshold", type=float, default=_DEFAULT_THRESHOLD,
        help=f"Compaction threshold (default: {_DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show grouping boundaries without running summarizer",
    )
    parser.add_argument(
        "--skip-judge", action="store_true",
        help="Run summarizer but skip LLM judge scoring",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save results to a timestamped file",
    )
    args = parser.parse_args()

    records = load_first_compaction_records(args.conv)
    print(f"Loaded {len(records)} first-compaction records")
    print(f"Context limit: {args.context_limit:,} tokens  Threshold: {args.threshold}")
    print(f"Testing keep_recent_groups: {args.groups}")
    print(f"Baseline: raw keep_recent=6")

    provider = get_provider() if not args.dry_run else None

    results = []
    for conv_id, messages in records:
        result = await run_eval(
            provider,
            conv_id,
            messages,
            args.groups,
            args.context_limit,
            args.threshold,
            dry_run=args.dry_run,
            skip_judge=args.skip_judge,
        )
        results.append(result)
        print_result(result)

    if not args.dry_run:
        print_summary_table(results)

    if args.save:
        runs_dir = Path(__file__).resolve().parent / "runs"
        runs_dir.mkdir(exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = runs_dir / f"grouping_eval_{ts}.json"
        # Strip summaries to save space
        for r in results:
            for cfg in r.get("configs", {}).values():
                cfg.pop("summary", None)
        save_path.write_text(json.dumps(results, indent=2))
        print(f"\nSaved to: {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
