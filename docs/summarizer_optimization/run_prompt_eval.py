"""Summarizer prompt/truncation eval runner.

Replays real SummaryRecord inputs through multiple config variants and
prints side-by-side summaries so you can judge quality differences.

Configs tested:
  A (baseline)  — old prompt, all tools capped at 200 chars
  B (prompt)    — new prompt, all tools capped at 200 chars
  C (full)      — new prompt, per-tool caps (code=1500, browser=500)

Usage:
  PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py
  PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py --record fc31d282
  PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py --skip-baseline
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import re
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PROMPT_OLD = (
    "You are a summarizer. Condense the following conversation into a factual "
    "reference document that the assistant can use to continue working.\n"
    "\n"
    "You MUST use EXACTLY this structure with these exact headings. Do not use "
    "any other format. Do not write prose or commentary. Start your response "
    "with '## Completed Work'.\n"
    "\n"
    "## Completed Work\n"
    "List every fact, finding, and result produced so far as bullet points.\n"
    "Focus on RESULTS and FINDINGS, not the steps taken to get them.\n"
    "\n"
    "## Key Data\n"
    "List all specific reference data the user needs to act on the results:\n"
    "URLs/links, prices, ratings, dates, addresses, phone numbers, file paths,\n"
    "code snippets, error messages, version numbers, etc.\n"
    "Format as a structured list. If no key data was gathered, write \"None\".\n"
    "\n"
    "## Current State\n"
    "Describe what is happening RIGHT NOW at the end of the conversation.\n"
    "What page or application is open? What was the assistant doing in its\n"
    "last message? What did the user most recently ask for? Include any\n"
    "in-progress work, unresolved errors, or pending actions.\n"
    "If not applicable, write \"None\".\n"
    "\n"
    "RULES:\n"
    "- Your output MUST start with '## Completed Work' and contain all three "
    "sections above. No other format is acceptable.\n"
    "- Preserve FACTS and DATA, not process. Omit HOW results were obtained "
    "(clicks, navigation, scrolling, filter adjustments, retries, error recovery). "
    "Do not describe tool calls, UI interactions, or troubleshooting steps.\n"
    "  WRONG: 'Navigated to Google Flights, set origin to AUS, applied nonstop "
    "filter, clicked search'\n"
    "  RIGHT: 'Searched Google Flights for nonstop AUS→ORD Apr 10-12. Best "
    "options: American $634, United $714, Delta $558'\n"
    "- MUST INCLUDE URLs needed to revisit results or continue work (product pages, "
    "booking pages, data sources, file paths). Omit intermediate navigation URLs "
    "(search engines, category listings, filter pages).\n"
    "- MUST INCLUDE all prices, ratings, quantities, dates, and numerical data "
    "found. These are the primary value of the research.\n"
    "- If the input contains a prior summary, merge ALL its facts into yours — "
    "every URL, price, name, date, and detail from the prior summary MUST appear "
    "in your output. Do not summarize the summary; expand it with new facts.\n"
    "- Never drop specific details (numbers, names, URLs, paths, code) in favor of "
    "vague descriptions like 'highly-rated' or 'well-known'.\n"
    "- Be concise but exhaustive in facts.\n"
    "- Do NOT echo these instructions — replace them with actual content."
)

_PROMPT_NEW = (
    "You are a summarizer. Condense the following conversation into a factual "
    "reference document that the assistant can use to continue working. The "
    "conversation may be browser research, code analysis, or both.\n"
    "\n"
    "You MUST use EXACTLY this structure with these exact headings. Do not use "
    "any other format. Do not write prose or commentary. Start your response "
    "with '## Completed Work'.\n"
    "\n"
    "## Completed Work\n"
    "List every fact, finding, and result produced so far as bullet points.\n"
    "Focus on RESULTS and FINDINGS, not the steps taken to get them.\n"
    "For code tasks: document what key files CONTAIN (APIs, class definitions, "
    "critical logic, function signatures), not just that files were read.\n"
    "For research tasks: document what was found at each source.\n"
    "\n"
    "## Key Data\n"
    "List all specific reference data needed to continue the work:\n"
    "- Research: URLs/links, prices, ratings, dates, addresses, phone numbers, "
    "version numbers\n"
    "- Code: file paths, function/method signatures, class definitions, API "
    "contracts, import paths, error messages, test results, shell command output\n"
    "Format as a structured list grouped by type. If no key data was gathered, "
    "write \"None\".\n"
    "\n"
    "## Current State\n"
    "Describe what is happening RIGHT NOW at the end of the conversation.\n"
    "What was the assistant doing in its last message? What did the user most "
    "recently ask for? Include any in-progress work, unresolved errors, or "
    "pending actions. If not applicable, write \"None\".\n"
    "\n"
    "RULES:\n"
    "- Your output MUST start with '## Completed Work' and contain all three "
    "sections above. No other format is acceptable.\n"
    "- Preserve FACTS and DATA, not process.\n"
    "  Browser WRONG: 'Navigated to Google Flights, applied nonstop filter, "
    "clicked search'\n"
    "  Browser RIGHT: 'Searched Google Flights nonstop AUS→ORD Apr 10-12. "
    "Best: American $634, United $714, Delta $558'\n"
    "  Code WRONG: 'Read sdk/events/_dispatcher.py'\n"
    "  Code RIGHT: 'EventDispatcher (sdk/events/_dispatcher.py): async pub/sub, "
    "subscribe(handler)/unsubscribe()/publish(event) methods, supports async "
    "context manager'\n"
    "- For code: preserve key signatures, field names, and behavioural details "
    "found in file contents — these are the primary value of code analysis.\n"
    "- For research: MUST INCLUDE URLs needed to revisit results. Omit "
    "intermediate navigation URLs (search engines, category listings).\n"
    "- MUST INCLUDE all prices, ratings, quantities, dates, and numerical data.\n"
    "- If the input contains a prior summary, merge ALL its facts into yours — "
    "every URL, price, name, date, path, and signature MUST appear in your "
    "output. Do not summarize the summary; expand it with new facts.\n"
    "- Never drop specific details (numbers, names, URLs, paths, signatures) in "
    "favor of vague descriptions like 'highly-rated' or 'well-known'.\n"
    "- Be concise but exhaustive in facts.\n"
    "- Do NOT echo these instructions — replace them with actual content."
)

# ---------------------------------------------------------------------------
# Serialization helpers (inline — no project imports needed)
# ---------------------------------------------------------------------------

_SUMMARY_PREFIX = "[Conversation summary — earlier messages were compacted]\n\n"
_THINKING_CAP = 200

_TOOL_ARG_KEYS: dict[str, list[str]] = {
    "write_file": ["path"], "read_file": ["path"],
    "apply_text_patch": ["path"], "replace_in_file": ["path"],
    "run_bash_cmd": ["cmd", "command"], "open_url": ["url"],
    "click": ["selector", "ref"], "fill_field": ["selector", "ref"],
    "grep": ["pattern", "query"], "list_dir": ["path"],
    "generate_image": ["prompt"], "describe_image": ["path", "image_path"],
}

_TRIVIAL_PATTERNS = [
    "{'success': True", '{"success": true',
    "{'stdout': None, 'stderr': None, 'exit_code': 0}",
    "{'stdout': '', 'stderr': None, 'exit_code': 0}",
    "{'stdout': '', 'stderr': '', 'exit_code': 0}",
    "{'stdout': None, 'stderr': '', 'exit_code': 0}",
]

_PAGE_PREFIX_RE = re.compile(r"^\[Page: .+? \| (https?://[^\s|]+)")


def _is_trivial(content: str) -> bool:
    s = content.strip()
    if not s:
        return True
    return any(s.startswith(p) and len(s) < 200 for p in _TRIVIAL_PATTERNS)


def _summarize_tool_args(tool_name: str, fn: dict) -> str:
    keys = _TOOL_ARG_KEYS.get(tool_name)
    if not keys:
        return ""
    raw = fn.get("arguments", {})
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return ""
    if not isinstance(raw, dict):
        return ""
    parts = [str(raw[k])[:200] for k in keys if raw.get(k) is not None]
    return ", ".join(parts)


def _dedup_snapshots(messages: list[dict]) -> None:
    last_seen: dict[str, int] = {}
    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            continue
        c = m.get("content") or ""
        match = _PAGE_PREFIX_RE.match(c)
        if match:
            base = match.group(1).split("?")[0]
            last_seen[base] = i
    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            continue
        c = m.get("content") or ""
        match = _PAGE_PREFIX_RE.match(c)
        if match:
            base = match.group(1).split("?")[0]
            if last_seen.get(base) != i:
                m["content"] = "[page snapshot — superseded by later snapshot]"


def serialize(messages: list[dict], caps: dict[str, int], default_cap: int = 200) -> str:
    _dedup_snapshots(messages)
    entries: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if content.startswith(_SUMMARY_PREFIX):
            continue
        if role == "assistant":
            tcs = msg.get("tool_calls")
            thinking = (msg.get("thinking") or "")[:_THINKING_CAP]
            if len(msg.get("thinking") or "") > _THINKING_CAP:
                thinking += "..."
            if tcs:
                parts = []
                for tc in tcs:
                    fn = tc.get("function", {})
                    name = fn.get("name", "unknown")
                    args = _summarize_tool_args(name, fn)
                    parts.append(f"{name}({args})" if args else name)
                ts = ", ".join(parts)
                if content and thinking:
                    entries.append(f"Assistant: {content}\n  (thinking: {thinking})\n  [Called: {ts}]")
                elif content:
                    entries.append(f"Assistant: {content}\n  [Called: {ts}]")
                elif thinking:
                    entries.append(f"Assistant (thinking: {thinking})\n  [Called: {ts}]")
                else:
                    entries.append(f"Assistant: [Called: {ts}]")
            elif content and thinking:
                entries.append(f"Assistant: {content}\n  (thinking: {thinking})")
            elif content:
                entries.append(f"Assistant: {content}")
            elif thinking:
                entries.append(f"Assistant (thinking: {thinking})")
        elif role == "tool":
            tool_name = msg.get("tool_name", "unknown")
            if _is_trivial(content):
                continue
            cap = caps.get(tool_name, default_cap)
            if len(content) > cap:
                content = content[:cap] + "..."
            entries.append(f"Tool ({tool_name}): {content}")
        elif role == "user":
            entries.append(f"User: {content}")
    return "\n\n".join(entries)


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------

_CAPS_OLD: dict[str, int] = {}  # all default to 200

# Production caps: code tools at 1500, browser tools at 400-800.
# Higher caps (6k, 40k) were tested and broke kimi: the model starts treating
# the large file dumps as an in-progress task to continue rather than a
# conversation to summarize. Agent messages already synthesize key signatures,
# so raw file content beyond ~1500 chars adds noise, not signal.
_CAPS_NEW: dict[str, int] = {
    "read_file": 1500, "grep": 1500, "run_bash_cmd": 1500, "list_dir": 800,
    "apply_text_patch": 400, "replace_in_file": 400, "write_file": 300,
    "open_url": 500, "read_page": 800, "browse_page": 500, "scroll_page": 400,
}

_CONFIGS = [
    ("A-baseline", _PROMPT_OLD, _CAPS_OLD),
    ("B-prompt",   _PROMPT_NEW, _CAPS_OLD),
    ("C-full",     _PROMPT_NEW, _CAPS_NEW),
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "kimi-k2.5:cloud"


def call_kimi(prompt: str, user_content: str) -> tuple[str, float, str]:
    """Return (summary_text, elapsed_seconds, done_reason)."""
    t0 = time.monotonic()
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {"num_ctx": 131072, "num_predict": 8192, "temperature": 0.3},
    }, timeout=300)
    elapsed = time.monotonic() - t0
    if resp.status_code != 200:
        return f"[ERROR {resp.status_code}]: {resp.text[:200]}", elapsed, "error"
    data = resp.json()
    return data["message"]["content"], elapsed, data.get("done_reason", "?")


def load_records(record_filter: str | None, include_nudge: bool = False) -> list[tuple[str, dict]]:
    pattern = os.path.expanduser("~/.computron_9000/conversations/*/summaries/*.json")
    records = []
    for path in sorted(glob.glob(pattern)):
        record_id = Path(path).stem
        if record_filter and record_filter not in record_id and record_filter not in path:
            continue
        with open(path) as f:
            data = json.load(f)
        is_nudge = data.get("model") == "nudge"
        # Skip nudge records unless explicitly requested — they have no LLM-generated
        # baseline to compare against, but are useful for evaluating code task caps.
        if is_nudge and not include_nudge:
            continue
        # Skip very small records
        if (data.get("messages_compacted") or 0) < 10:
            continue
        records.append((path, data))
    return records


def run(args: argparse.Namespace) -> None:
    records = load_records(args.record, include_nudge=args.include_nudge)
    if not records:
        print("No matching records found.")
        return

    for path, record in records:
        conv_id = path.split("/")[-3][:12]
        agent = record.get("agent_name", "?")
        n_msgs = record.get("messages_compacted", 0)
        orig_model = record.get("model", "?")
        print(f"\n{'=' * 72}")
        print(f"Record: {Path(path).stem[:8]}  conv={conv_id}  agent={agent}  msgs={n_msgs}  original_model={orig_model}")

        results: dict[str, tuple[str, float, int, str]] = {}

        for cfg_name, prompt, caps in _CONFIGS:
            if args.skip_baseline and cfg_name == "A-baseline":
                continue
            serialized = serialize(copy.deepcopy(record["input_messages"]), caps)
            print(f"\n  [{cfg_name}] input={len(serialized):,} chars  calling {MODEL}...", flush=True)
            summary, elapsed, done = call_kimi(prompt, serialized)
            results[cfg_name] = (summary, elapsed, len(serialized), done)
            print(f"  [{cfg_name}] → {len(summary)} chars in {elapsed:.1f}s (done={done})")

        # Print summaries
        for cfg_name, (summary, elapsed, input_chars, done) in results.items():
            print(f"\n{'─' * 72}")
            print(f"  CONFIG {cfg_name}  ({input_chars:,} input chars → {len(summary)} output chars, {elapsed:.1f}s)")
            print(f"{'─' * 72}")
            print(summary)

        if not args.skip_baseline and "A-baseline" in results and orig_model != "nudge":
            orig_summary = record.get("summary_text", "(none)")
            print(f"\n{'─' * 72}")
            print(f"  ORIGINAL ({orig_model}) — {len(orig_summary)} chars")
            print(f"{'─' * 72}")
            print(orig_summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarizer prompt/truncation eval")
    parser.add_argument("--record", help="Filter to records matching this string (id or path substring)")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip config A (baseline)")
    parser.add_argument("--include-nudge", action="store_true",
                        help="Include nudge records (no LLM baseline, but useful for code task cap evaluation)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
