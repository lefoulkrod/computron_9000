"""Run summarizer scenarios from markdown files.

Discovers scenario files in docs/summarizer_optimization/scenarios/,
parses them, runs the summarizer, and checks continuity via probes.

Run with:
    PYTHONPATH=. uv run pytest tests/sdk/context/test_scenarios.py -v -s
"""

import copy
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from sdk.context._strategy import SummarizeStrategy, _serialize_messages
from sdk.providers import get_provider

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "summarizer_optimization"
    / "scenarios"
)

# Capable cloud model for continuity probes. We're testing summary quality,
# not the probe model — so use something that will reliably answer correctly
# IF the summary is good.
_PROBE_MODEL = "kimi-k2.5:cloud"

# ---------------------------------------------------------------------------
# Data structures
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
# Markdown parser
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
    """Parse a scenario markdown file into a Scenario."""
    text = filepath.read_text()
    blocks = _extract_code_blocks(text)
    phases = [msgs for b in blocks if (msgs := _parse_messages(b))]
    return _Scenario(
        name=filepath.stem,
        phases=phases,
        required_facts=_extract_facts(text),
        probes=_extract_probes(text),
        threshold=_extract_threshold(text),
    )


def _extract_code_blocks(text: str) -> list[str]:
    """Extract fenced code blocks under Conversation / Phase headings."""
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
    """Parse human-readable conversation format into message dicts."""
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
    """Split a markdown table row on | delimiters, respecting backtick spans."""
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
    """Extract regex pattern from a table cell like `r\"pattern\"`."""
    m = re.search(r'`r"(.+?)"`', cell)
    if not m:
        m = re.search(r"`r'(.+?)'`", cell)
    return m.group(1) if m else None


def _extract_facts(text: str) -> list[_RequiredFact]:
    """Extract required facts from tables with regex pattern columns."""
    facts: list[_RequiredFact] = []
    for line in text.split("\n"):
        if "|" not in line or '`r"' not in line:
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
    """Extract continuity probes from the ## Probes section."""
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
    """Extract minimum fact retention threshold."""
    m = re.search(r"\*\*Minimum threshold\*\*:\s*(\d+)%", text)
    if m:
        return int(m.group(1)) / 100.0
    return 0.75


# ---------------------------------------------------------------------------
# Probe runner
# ---------------------------------------------------------------------------


# How many recent messages the agent keeps verbatim (matches production).
_KEEP_RECENT = 6


async def _probe_agent(
    system_prompt: str,
    first_user_msg: str,
    summary: str,
    kept_recent_text: str,
    question: str,
) -> str:
    """Simulate what the agent sees after compaction and ask a question.

    Builds the same context the real agent would have:
    system prompt + pinned first user message + summary + kept recent
    messages + the probe question.
    """
    provider = get_provider()
    context = summary
    if kept_recent_text:
        context += (
            "\n\n--- Recent messages (not summarized) ---\n\n"
            + kept_recent_text
        )

    response = await provider.chat(
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
    )
    return response.message.content or ""


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def _discover_scenarios() -> list[Path]:
    if not _SCENARIOS_DIR.exists():
        return []
    return sorted(_SCENARIOS_DIR.glob("*.md"))


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario_path",
    _discover_scenarios(),
    ids=[p.stem for p in _discover_scenarios()],
)
async def test_scenario(scenario_path: Path) -> None:
    """Run a scenario: summarize, then check continuity via probes."""
    scenario = _parse_scenario(scenario_path)
    strategy = SummarizeStrategy()

    # --- Summarize each phase, feeding summary forward ---
    prior_summary = None
    summary_text = ""
    total_time = 0.0

    for phase_messages in scenario.phases:
        messages_copy = copy.deepcopy(phase_messages)
        conversation_text = _serialize_messages(messages_copy)
        start = time.perf_counter()
        summary_text, _model = await strategy._call_summarizer(
            conversation_text, prior_summary,
        )
        elapsed = time.perf_counter() - start
        total_time += elapsed
        prior_summary = summary_text

    # --- Fact retention (informational proxy) ---
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

    # --- Print summary results ---
    print(f"\n{'=' * 70}")
    print(f"Scenario: {scenario.name}")
    print(f"Phases: {len(scenario.phases)} | Summarization time: {total_time:.1f}s")
    print(f"Summary: {len(summary_text):,} chars")
    print(f"{'=' * 70}")
    print(summary_text)
    print(f"{'=' * 70}")

    if scenario.required_facts:
        print(
            f"Fact retention: {facts_found}/{len(scenario.required_facts)}"
            f" ({retention:.0%})"
        )
        for desc, found in fact_results:
            print(f"  {'✓' if found else '✗'} {desc}")

    # --- Build post-compaction context (matches production) ---
    system_prompt = ""
    first_user_msg = ""
    for msg in scenario.phases[0]:
        if msg.get("role") == "system" and not system_prompt:
            system_prompt = msg.get("content", "")
        elif msg.get("role") == "user" and not first_user_msg:
            first_user_msg = msg.get("content", "")

    # Kept recent: last N non-system messages from the final phase
    last_phase = scenario.phases[-1]
    non_system = [m for m in last_phase if m.get("role") != "system"]
    kept_msgs = non_system[-_KEEP_RECENT:] if len(non_system) > _KEEP_RECENT else non_system
    kept_recent_text = _serialize_messages(copy.deepcopy(kept_msgs))

    # --- Continuity probes ---
    probe_failures: list[str] = []
    if scenario.probes:
        print(f"\n{'=' * 70}")
        print("Continuity probes:")
        for probe in scenario.probes:
            response = await _probe_agent(
                system_prompt, first_user_msg, summary_text,
                kept_recent_text, probe.question,
            )
            pass_ok = bool(
                re.search(probe.pass_pattern, response, re.IGNORECASE),
            )
            fail_ok = (
                not bool(re.search(probe.fail_pattern, response, re.IGNORECASE))
                if probe.fail_pattern
                else True
            )
            passed = pass_ok and fail_ok
            status = "✓" if passed else "✗"

            print(f"  {status} Q: {probe.question}")
            print(f"    A: {response}")

            if not pass_ok:
                print(
                    f"    FAIL: expected pattern"
                    f" /{probe.pass_pattern}/ not found"
                )
                probe_failures.append(
                    f"'{probe.question}': expected /{probe.pass_pattern}/",
                )
            if not fail_ok:
                print(
                    f"    FAIL: anti-pattern"
                    f" /{probe.fail_pattern}/ found"
                )
                probe_failures.append(
                    f"'{probe.question}': anti-pattern /{probe.fail_pattern}/",
                )

    print(f"{'=' * 70}")

    # --- Assert ---
    assert len(summary_text) > 50, "Summary is too short"
    assert not probe_failures, (
        "Continuity probe failures:\n"
        + "\n".join(f"  - {f}" for f in probe_failures)
    )
