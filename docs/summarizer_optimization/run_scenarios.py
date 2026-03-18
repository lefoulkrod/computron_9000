#!/usr/bin/env python3
"""Standalone scenario runner for summarizer optimization.

NOT a pytest test — run directly:
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py --model qwen3.5:4b
    PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py --scenario 05
"""

import argparse
import asyncio
import copy
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sdk.context._strategy import SummarizeStrategy, _serialize_messages
from sdk.providers import get_provider

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
_PROBE_MODEL = "kimi-k2.5:cloud"
_SUMMARIZE_TIMEOUT = 300  # 5 minutes — fail if longer
_PROBE_TIMEOUT = 120  # 2 minutes per probe

# ---------------------------------------------------------------------------
# Data structures (same as test_scenarios.py parser)
# ---------------------------------------------------------------------------

@dataclass
class _RequiredFact:
    description: str
    pattern: str

@dataclass
class _Probe:
    question: str
    pass_pattern: str
    fail_pattern: str | None

@dataclass
class _Scenario:
    name: str
    phases: list[list[dict]]
    required_facts: list[_RequiredFact]
    probes: list[_Probe]
    threshold: float

# ---------------------------------------------------------------------------
# Parser (duplicated from test to avoid import issues)
# ---------------------------------------------------------------------------

_ROLE_RE = re.compile(
    r"^(?:"
    r"(?P<system>system):\s*(?P<sys_content>.*)"
    r"|(?P<user>user):\s*(?P<user_content>.*)"
    r"|(?P<assistant>A):\s*(?P<asst_content>.*)"
    r"|tool\s*\((?P<tool_name>[^)]+)\):\s*(?P<tool_content>.*)"
    r")$",
)
_TOOL_CALLS_RE = re.compile(r"\[Called tools?:\s*([^\]]+)\]")


def _parse_scenario(filepath: Path) -> _Scenario:
    text = filepath.read_text()

    # Check if this scenario references an external conversation file
    conv_match = re.search(
        r"Conversation ID:\s*`([0-9a-f-]+)`", text,
    )
    if conv_match:
        phases = _load_conversation_phases(conv_match.group(1))
    else:
        blocks = _extract_code_blocks(text)
        phases = [msgs for b in blocks if (msgs := _parse_messages(b))]

    return _Scenario(
        name=filepath.stem,
        phases=phases,
        required_facts=_extract_facts(text),
        probes=_extract_probes(text),
        threshold=_extract_threshold(text),
    )


def _load_conversation_phases(conv_id: str) -> list[list[dict]]:
    """Load a real conversation from stored history as a single phase."""
    conv_dir = Path.home() / ".computron_9000" / "conversations"
    history_file = conv_dir / f"{conv_id}_history.json"
    if not history_file.exists():
        # Try without _history suffix
        history_file = conv_dir / f"{conv_id}.json"
    if not history_file.exists():
        print(f"  WARNING: conversation file not found for {conv_id}")
        return []

    import json
    data = json.load(open(history_file))
    msgs = data if isinstance(data, list) else data.get("messages", [])

    # Return non-system messages (minus pinned first user and kept recent)
    # as a single phase for compaction
    non_system = [m for m in msgs if m.get("role") != "system"]
    if len(non_system) <= 7:
        return [non_system]

    # Compactable = skip pinned first user, skip last keep_recent
    compactable = non_system[1:-_KEEP_RECENT]
    return [compactable]


def _extract_code_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    in_conversation = False
    in_code_block = False
    current: list[str] = []
    for line in text.split("\n"):
        if re.match(r"^#{2,3}\s+(Conversation|Phase\s)", line):
            in_conversation = True
        elif re.match(r"^##\s+(?!Conversation)", line) and not line.startswith("###"):
            in_conversation = False
        if in_conversation:
            if line.strip().startswith("```"):
                if in_code_block:
                    blocks.append("\n".join(current))
                    current = []
                    in_code_block = False
                else:
                    in_code_block = True
            elif in_code_block:
                current.append(line)
    return blocks


def _parse_messages(text: str) -> list[dict]:
    messages: list[dict] = []
    current_role: str | None = None
    current_tool_name: str | None = None
    content_lines: list[str] = []

    def flush() -> None:
        nonlocal current_role, current_tool_name, content_lines
        if current_role is None:
            return
        content = "\n".join(content_lines).strip()
        msg: dict = {"role": current_role}
        if current_role == "tool":
            msg["tool_name"] = current_tool_name
            msg["content"] = content
        elif current_role == "assistant":
            m = _TOOL_CALLS_RE.search(content)
            if m:
                tool_names = [t.strip() for t in m.group(1).split(",")]
                msg["tool_calls"] = [
                    {"function": {"name": n, "arguments": {}}}
                    for n in tool_names
                ]
                content = (content[: m.start()] + content[m.end() :]).strip()
            msg["content"] = content if content else None
        else:
            msg["content"] = content
        messages.append(msg)
        current_role = None
        current_tool_name = None
        content_lines = []

    for line in text.split("\n"):
        m = _ROLE_RE.match(line)
        if m:
            flush()
            if m.group("system") is not None:
                current_role = "system"
                content_lines = [m.group("sys_content")]
            elif m.group("user") is not None:
                current_role = "user"
                content_lines = [m.group("user_content")]
            elif m.group("assistant") is not None:
                current_role = "assistant"
                content_lines = [m.group("asst_content")]
            elif m.group("tool_name") is not None:
                current_role = "tool"
                current_tool_name = m.group("tool_name")
                content_lines = [m.group("tool_content")]
        elif current_role is not None and line.strip():
            content_lines.append(line.lstrip())
    flush()
    return messages


def _split_table_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    in_backtick = False
    for char in line:
        if char == "`":
            in_backtick = not in_backtick
            current.append(char)
        elif char == "|" and not in_backtick:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return [c for c in cells if c]


def _extract_pattern(cell: str) -> str | None:
    m = re.search(r'`r"(.+?)"`', cell)
    if not m:
        m = re.search(r"`r'(.+?)'`", cell)
    return m.group(1) if m else None


def _extract_facts(text: str) -> list[_RequiredFact]:
    facts: list[_RequiredFact] = []
    in_facts = False
    for line in text.split("\n"):
        if re.match(r"^#{2,3}\s+.*[Rr]equired [Ff]acts", line):
            in_facts = True
            continue
        if re.match(r"^##\s+", line) and in_facts and not line.startswith("###"):
            in_facts = False
            continue
        if not in_facts or "|" not in line or '`r"' not in line:
            continue
        if re.match(r"^\s*\|[-\s|]+\|\s*$", line):
            continue
        cells = _split_table_row(line)
        if len(cells) < 2:
            continue
        desc = cells[0]
        pattern = _extract_pattern(cells[1])
        if desc and pattern:
            facts.append(_RequiredFact(desc, pattern))
    return facts


def _extract_probes(text: str) -> list[_Probe]:
    probes: list[_Probe] = []
    in_probes = False
    for line in text.split("\n"):
        if re.match(r"^##\s+Probes", line):
            in_probes = True
            continue
        if re.match(r"^##\s+", line) and in_probes:
            in_probes = False
            continue
        if not in_probes or "|" not in line:
            continue
        if re.match(r"^\s*\|[-\s|]+\|\s*$", line):
            continue
        cells = _split_table_row(line)
        if len(cells) < 2:
            continue
        question = cells[0]
        if "Question" in question or "Probe" in question:
            continue
        pass_pattern = _extract_pattern(cells[1]) if len(cells) > 1 else None
        fail_cell = cells[2] if len(cells) > 2 else ""
        fail_pattern = (
            _extract_pattern(fail_cell)
            if fail_cell and fail_cell.strip() != "—"
            else None
        )
        if question and pass_pattern:
            probes.append(_Probe(question, pass_pattern, fail_pattern))
    return probes


def _extract_threshold(text: str) -> float:
    m = re.search(r"\*\*Minimum threshold\*\*:\s*(\d+)%", text)
    if m:
        return int(m.group(1)) / 100.0
    return 0.75


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_KEEP_RECENT = 6


async def _probe_agent(
    system_prompt: str,
    first_user_msg: str,
    summary: str,
    kept_recent_text: str,
    question: str,
) -> str:
    provider = get_provider()
    context = summary
    if kept_recent_text:
        context += (
            "\n\n--- Recent messages (not summarized) ---\n\n"
            + kept_recent_text
        )
    response = await asyncio.wait_for(
        provider.chat(
            model=_PROBE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": first_user_msg},
                {
                    "role": "user",
                    "content": (
                        "[Conversation summary — earlier messages were"
                        " compacted]\n\n" + context
                    ),
                },
                {"role": "user", "content": question},
            ],
            think=False,
            options={"temperature": 0, "num_ctx": 8192},
        ),
        timeout=_PROBE_TIMEOUT,
    )
    return response.message.content or ""


async def run_scenario(
    scenario_path: Path,
    summary_model: str | None = None,
) -> dict:
    """Run a single scenario. Returns results dict."""
    scenario = _parse_scenario(scenario_path)
    strategy = SummarizeStrategy(summary_model=summary_model)

    # --- Summarize ---
    prior_summary = None
    summary_text = ""
    total_time = 0.0

    for phase_messages in scenario.phases:
        messages_copy = copy.deepcopy(phase_messages)
        conversation_text = _serialize_messages(messages_copy)
        start = time.perf_counter()
        try:
            coro = strategy._call_summarizer(conversation_text, prior_summary)
            summary_text, _model = await asyncio.wait_for(
                coro, timeout=_SUMMARIZE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return {
                "name": scenario.name,
                "status": "TIMEOUT",
                "time": _SUMMARIZE_TIMEOUT,
            }
        elapsed = time.perf_counter() - start
        total_time += elapsed
        prior_summary = summary_text

    # --- Fact retention ---
    facts_found = 0
    fact_results: list[tuple[str, bool]] = []
    for fact in scenario.required_facts:
        found = bool(re.search(fact.pattern, summary_text, re.IGNORECASE))
        facts_found += int(found)
        fact_results.append((fact.description, found))
    retention = (
        facts_found / len(scenario.required_facts)
        if scenario.required_facts
        else 1.0
    )

    # --- Print summary ---
    print(f"\n{'=' * 70}")
    print(f"Scenario: {scenario.name}")
    print(f"Phases: {len(scenario.phases)} | Time: {total_time:.1f}s")
    print(f"Summary: {len(summary_text):,} chars")
    print(f"{'=' * 70}")
    print(summary_text)
    print(f"{'=' * 70}")
    if scenario.required_facts:
        print(f"Fact retention: {facts_found}/{len(scenario.required_facts)} ({retention:.0%})")
        for desc, found in fact_results:
            print(f"  {'✓' if found else '✗'} {desc}")

    # --- Probes ---
    system_prompt = ""
    first_user_msg = ""
    for msg in scenario.phases[0]:
        if msg.get("role") == "system" and not system_prompt:
            system_prompt = msg.get("content", "")
        elif msg.get("role") == "user" and not first_user_msg:
            first_user_msg = msg.get("content", "")

    last_phase = scenario.phases[-1]
    non_system = [m for m in last_phase if m.get("role") != "system"]
    kept_msgs = non_system[-_KEEP_RECENT:] if len(non_system) > _KEEP_RECENT else non_system
    kept_recent_text = _serialize_messages(copy.deepcopy(kept_msgs))

    probe_pass = 0
    probe_total = 0
    probe_failures: list[str] = []

    if scenario.probes:
        print(f"\nContinuity probes:")
        for probe in scenario.probes:
            probe_total += 1
            try:
                response = await _probe_agent(
                    system_prompt, first_user_msg, summary_text,
                    kept_recent_text, probe.question,
                )
            except asyncio.TimeoutError:
                print(f"  TIMEOUT Q: {probe.question}")
                probe_failures.append(f"'{probe.question}': probe timed out")
                continue

            _flags = re.IGNORECASE | re.DOTALL
            pass_ok = bool(re.search(probe.pass_pattern, response, _flags))
            fail_ok = (
                not bool(re.search(probe.fail_pattern, response, _flags))
                if probe.fail_pattern
                else True
            )
            passed = pass_ok and fail_ok
            status = "✓" if passed else "✗"
            if passed:
                probe_pass += 1

            print(f"  {status} Q: {probe.question}")
            print(f"    A: {response}")
            if not pass_ok:
                print(f"    FAIL: expected /{probe.pass_pattern}/ not found")
                probe_failures.append(f"'{probe.question}': expected /{probe.pass_pattern}/")
            if not fail_ok:
                print(f"    FAIL: anti-pattern /{probe.fail_pattern}/ found")
                probe_failures.append(f"'{probe.question}': anti-pattern /{probe.fail_pattern}/")

    print(f"{'=' * 70}")

    return {
        "name": scenario.name,
        "status": "PASS" if not probe_failures else "FAIL",
        "probes": f"{probe_pass}/{probe_total}",
        "time": round(total_time, 1),
        "length": len(summary_text),
        "fact_retention": f"{facts_found}/{len(scenario.required_facts)} ({retention:.0%})",
        "failures": probe_failures,
    }


def _unload_model(model: str) -> None:
    """Unload a model from Ollama to free VRAM."""
    try:
        subprocess.run(
            ["ollama", "stop", model],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run summarizer scenarios")
    parser.add_argument("--model", default=None, help="Summary model override")
    parser.add_argument("--scenario", default=None, help="Run only scenarios matching this substring")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    args = parser.parse_args()

    scenarios = sorted(_SCENARIOS_DIR.glob("*.md"))
    if args.scenario:
        scenarios = [s for s in scenarios if args.scenario in s.stem]

    if not scenarios:
        print("No scenarios found")
        return

    model_label = args.model or "config default"
    print(f"Model: {model_label}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Runs: {args.runs}")
    print()

    for run in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"{'=' * 70}")
            print(f"RUN {run}/{args.runs}")
            print(f"{'=' * 70}")

        results = []
        for scenario_path in scenarios:
            result = await run_scenario(scenario_path, args.model)
            results.append(result)

        # Summary table
        print(f"\n{'=' * 70}")
        print(f"RESULTS (run {run})")
        print(f"{'=' * 70}")
        for r in results:
            if r["status"] == "TIMEOUT":
                print(f"  {r['name']:<30} TIMEOUT (>{_SUMMARIZE_TIMEOUT}s)")
            else:
                print(
                    f"  {r['name']:<30} probes={r['probes']}  "
                    f"time={r['time']}s  length={r['length']:,}  "
                    f"facts={r['fact_retention']}  {r['status']}"
                )

    # Unload the summary model after testing
    if args.model:
        print(f"\nUnloading {args.model}...")
        _unload_model(args.model)
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
