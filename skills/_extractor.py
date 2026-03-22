"""Background skill extraction loop.

Analyzes stored conversations during idle time to discover repeatable
patterns and extract them as reusable skills.

Uses a two-phase extraction approach:
  Phase 1 (Analyze) — feed the full untruncated transcript to the LLM to
  distill the goal, golden path, struggles, and site quirks.
  Phase 2 (Extract) — feed the concise analysis to the extraction prompt
  to produce the skill JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from config import load_config
from conversations import (
    TurnRecord,
    list_conversations,
    load_conversation_history,
    load_conversation_turns,
    load_sub_agent_histories,
    mark_conversation_analyzed,
)

from sdk.providers import get_provider

from ._models import SkillDefinition, SkillStep
from ._registry import add_skill, get_skill

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Phase 1: Analysis prompt
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT = """\
Analyze this agent session transcript. Your job is to produce a structured
analysis that a second LLM pass will use to build a reusable skill definition.

Focus on:
1. GOAL — what was the user trying to accomplish?
2. GOLDEN PATH — what is the minimum sequence of steps that actually worked?
   Strip out retries, mistakes, and dead ends. If the same pattern repeated
   for different inputs (e.g. searching 4 weekends), describe it ONCE as a
   parameterized loop.
3. STRUGGLES — where did the agent get confused or stuck? What was the
   recovery? These become warnings in the skill notes.
4. SITE QUIRKS — any site-specific behaviors that would trip up a naive
   agent (autocomplete dropdowns, dynamic content, form field ordering
   issues, elements that change after interaction, etc.)

Transcript:
{transcript}

Output a structured analysis in this format:
## Goal
...
## Golden Path
1. step (tool: tool_name) — description of what to do and why
2. ...
## Struggles & Recovery
- What went wrong → How it was fixed
## Site Quirks
- Quirk description and how to handle it
## Key Observations
- Any other useful patterns noticed
"""

# ---------------------------------------------------------------------------
# Phase 2: Extraction prompts (updated to accept pre-analyzed input)
# ---------------------------------------------------------------------------

# Conversation-level extraction prompt
_CONVERSATION_EXTRACTION_PROMPT = """\
You are given a pre-analyzed summary of a conversation between a user and an
AI assistant. Decide if it demonstrates a workflow worth saving as a reusable
skill.

REPLY NO (most conversations should be NO) unless ALL of these are true:
- The workflow has DOMAIN-SPECIFIC steps that would not be obvious without
  having done it before (e.g. specific URLs to visit, specific API sequences,
  non-trivial multi-step procedures with ordering constraints)
- The steps are PARAMETERIZABLE — swapping in different inputs would produce
  a meaningfully different but equally valid result
- Someone would realistically ask for this same type of task again

ALWAYS reply NO for these patterns — they are NOT skills:
- "Write code and run it" — that is what the agent does for every coding task
- "Delegate to a sub-agent, then output the result" — that is the generic
  agent pattern, not a domain-specific workflow
- Simple Q&A, brainstorming, or explanation conversations
- One-off creative tasks (make me a game, generate an image, write a song)
  unless the workflow involves a reproducible multi-step pipeline
- Tasks where the only "steps" are generic tool calls (run_bash_cmd,
  run_sub_agent, output_file) with task-specific arguments

Good skill examples: scraping a specific site's structure, deploying to a
specific platform with its required steps, a data pipeline that transforms
input through multiple specific tools, a research workflow that queries
multiple specific sources and cross-references them.

IMPORTANT guidelines for step construction:
- If a pattern repeats for different inputs, show it ONCE as a parameterized
  step with a note that it should be looped over the input list.
- Step "notes" MUST include real site-specific quirks, warnings, and recovery
  tips from the analysis — what to watch for, what can go wrong, how elements
  actually behave on the site.
- Do NOT fabricate CSS selectors or hardcode ref numbers. Describe elements
  by their role and visible text (e.g. "the 'From' input field", "the
  departure date picker").
- Do NOT include useless notes like "Ensure the selector is correct".

Analysis:
{transcript}

Required JSON schema for skill extraction:
{{
  "name": "snake_case_skill_name",
  "description": "What the skill accomplishes",
  "agent_scope": "COMPUTRON_9000 | BROWSER_AGENT | COMPUTER_AGENT | ANY",
  "trigger_patterns": ["natural language descriptions of when to use this"],
  "steps": [
    {{
      "description": "What this step does",
      "tool": "tool_function_name",
      "notes": "Site-specific quirks, warnings, recovery tips from the analysis"
    }}
  ]
}}

Reply with ONLY the JSON object or the word NO. No explanation."""

# Browser-agent-specific extraction prompt
_BROWSER_EXTRACTION_PROMPT = """\
You are given a pre-analyzed summary of a browser agent session. The agent
navigated web pages using tools like open_url, click, fill_field, read_page,
scroll_page, go_back, etc.

Extract the NAVIGATION PATTERN as a reusable skill if it demonstrates a
repeatable workflow for accomplishing a task on a specific website or type
of website. Focus on:
- Which URLs to visit and in what order
- What to look for on each page (element roles, visible text, page structure)
- What form fields to fill and how
- How to handle pagination, popups, or dynamic content
- What data to extract and how to structure it

REPLY NO if:
- The navigation was trivial (just opening a URL and reading it)
- The task was too site-specific with no parameterizable elements
- The agent was just browsing without a structured workflow

The steps should use the actual browser tool names (open_url, click,
fill_field, read_page, scroll_page, etc.) — NOT generic names like
"run_browser_agent_as_tool".

IMPORTANT guidelines for step construction:
- If the same action pattern repeats for different inputs (e.g. searching
  multiple dates), show it ONCE as a parameterized step with a note that
  it should be looped.
- Step "notes" MUST include real behavioral knowledge from the analysis —
  site quirks, what to watch for, what can go wrong, how elements actually
  behave on the site, and recovery strategies.
- Do NOT fabricate CSS selectors or hardcode ref numbers. Describe elements
  by their role and visible text (e.g. "the 'Depart' date input", "the
  first result link containing the price").
- Do NOT include useless notes like "Ensure the selector is correct".

Analysis:
{transcript}

Required JSON schema:
{{
  "name": "snake_case_skill_name",
  "description": "What the skill accomplishes",
  "agent_scope": "BROWSER_AGENT",
  "trigger_patterns": ["natural language descriptions of when to use this"],
  "steps": [
    {{
      "description": "What this step does",
      "tool": "open_url | click | fill_field | read_page | scroll_page | go_back | etc.",
      "notes": "Site-specific behavioral knowledge — quirks, warnings, recovery tips"
    }}
  ]
}}

Reply with ONLY the JSON object or the word NO. No explanation."""

# Map of agent name patterns to specialized prompts
_AGENT_PROMPTS: dict[str, str] = {
    "BROWSER": _BROWSER_EXTRACTION_PROMPT,
}


def _get_extraction_prompt(agent_name: str) -> str:
    """Return the best extraction prompt for a given agent name."""
    upper = agent_name.upper()
    for key, prompt in _AGENT_PROMPTS.items():
        if key in upper:
            return prompt
    return _CONVERSATION_EXTRACTION_PROMPT


# Refinement prompt for existing skills used in new conversations
_REFINEMENT_PROMPT = """\
This skill was applied but the agent adapted it. Should the skill be updated
to reflect the actual successful workflow?

Original skill steps:
{original_steps}

Actual conversation:
{transcript}

Output the updated skill JSON or just the word NO.

Required JSON schema:
{{
  "name": "{skill_name}",
  "description": "Updated description",
  "steps": [
    {{
      "description": "What this step does",
      "tool": "tool_function_name",
      "notes": ""
    }}
  ]
}}

Reply with ONLY the JSON object or the word NO."""


def _is_sub_agent_call(name: str) -> bool:
    """Check if a tool call name is a sub-agent invocation."""
    return name.startswith("run_") and name.endswith("_as_tool")


def _build_sub_agent_transcript(messages: list[dict[str, Any]], indent: str = "     ") -> str:
    """Build a full-fidelity transcript of a sub-agent's conversation."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "system":
            continue

        if role == "user":
            lines.append(f"{indent}[CONTEXT] {content}")
        elif role == "assistant":
            # Include reasoning text
            if content:
                lines.append(f"{indent}[REASONING] {content}")
            # Include thinking when present
            thinking = msg.get("thinking", "")
            if thinking:
                lines.append(f"{indent}[THINKING] {thinking}")
            # Include tool calls
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "unknown")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    args_str = args
                else:
                    args_str = ", ".join(
                        f"{k}={repr(v)}" for k, v in args.items()
                    )
                lines.append(f"{indent}> {name}({args_str})")
        elif role == "tool":
            tool_name = msg.get("tool_name") or msg.get("name", "unknown")
            result = content if content else "(empty)"
            lines.append(f"{indent}< {tool_name}: {result}")
    return "\n".join(lines)


def _build_conversation_transcript(
    messages: list[dict[str, Any]],
    sub_agent_histories: list[dict[str, Any]] | None = None,
) -> str:
    """Build a full-fidelity readable timeline from raw conversation history."""
    lines: list[str] = []
    # Index sub-agent histories by parent_tool for inline expansion
    _sub_agents_by_tool: dict[str, list[dict[str, Any]]] = {}
    for sa in (sub_agent_histories or []):
        key = sa.get("parent_tool", "")
        _sub_agents_by_tool.setdefault(key, []).append(sa)
    # Track consumption of sub-agent histories per tool name
    _sub_agent_cursors: dict[str, int] = {}

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "system":
            continue

        if role == "user":
            lines.append(f"[USER] {content}")
        elif role == "assistant":
            if content:
                lines.append(f"[ASSISTANT] {content}")
            # Include thinking when present
            thinking = msg.get("thinking", "")
            if thinking:
                lines.append(f"[THINKING] {thinking}")
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "unknown")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    args_str = args
                else:
                    args_str = ", ".join(
                        f"{k}={repr(v)}" for k, v in args.items()
                    )
                lines.append(f"  -> tool_call: {name}({args_str})")

                # For sub-agent calls, inline their internal steps
                if _is_sub_agent_call(name):
                    # Find the matching sub-agent history
                    func_name = f"run_{''.join(c.lower() if c.isalnum() else '_' for c in (args.get('agent_name', '') if isinstance(args, dict) else '')).strip('_') or 'agent'}_as_tool"
                    # Try matching by the tool function name first, fall back to the call name
                    for lookup_key in (func_name, name):
                        entries = _sub_agents_by_tool.get(lookup_key, [])
                        cursor = _sub_agent_cursors.get(lookup_key, 0)
                        if cursor < len(entries):
                            sa = entries[cursor]
                            _sub_agent_cursors[lookup_key] = cursor + 1
                            sa_name = sa.get("agent_name", "sub-agent")
                            sa_messages = sa.get("messages", [])
                            inner = _build_sub_agent_transcript(sa_messages)
                            if inner:
                                lines.append(f"     [{sa_name} internal steps]:")
                                lines.append(inner)
                            break
        elif role == "tool":
            tool_name = msg.get("tool_name") or msg.get("name", "unknown")
            result = content if content else "(empty)"
            lines.append(f"  <- {tool_name}: {result}")

    return "\n".join(lines) if lines else "(empty conversation)"


def _extract_tool_sequence_from_turns(turns: list[TurnRecord]) -> str:
    """Build a human-readable tool call sequence from turn records."""
    lines: list[str] = []
    for turn in turns:
        for msg in turn.messages:
            if msg.role == "tool" and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_summary = ", ".join(
                        f"{k}={repr(v)[:80]}" for k, v in tc.arguments.items()
                    )
                    status = "OK" if tc.success else "FAILED"
                    lines.append(
                        f"  [{msg.agent_name or turn.agent}] "
                        f"{tc.name}({args_summary}) → {status}"
                    )
    return "\n".join(lines) if lines else "(no tool calls)"


def _keyword_similarity(a: str, b: str) -> float:
    """Simple keyword overlap similarity between two strings."""
    words_a = set(re.split(r"\W+", a.lower())) - {"", "the", "a", "an", "to", "for", "and", "or", "in", "of"}
    words_b = set(re.split(r"\W+", b.lower())) - {"", "the", "a", "an", "to", "for", "and", "or", "in", "of"}
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _parse_skill_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from LLM output."""
    text = text.strip()
    if text.upper() == "NO":
        return None

    # Try to find JSON in the response
    start = text.find("{")
    if start == -1:
        return None

    # Find matching closing brace
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


async def _analyze_for_extraction(
    transcript: str,
    model: str,
    options: dict[str, Any] | None = None,
) -> str | None:
    """Phase 1: analyze full transcript into structured extraction input."""
    prompt = _ANALYSIS_PROMPT.format(transcript=transcript)
    try:
        provider = get_provider()
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        response = await provider.chat(model=model, messages=messages, options=options or {})
        result = response.message.content or ""
        # Sanity check — if the model returned something very short, it's useless
        if not result or len(result.strip()) < 50:
            return None
        return result.strip()
    except Exception:
        logger.exception("Analysis pass failed")
        return None


async def _analyze_conversation(
    conversation_id: str,
    messages: list[dict[str, Any]],
    turns: list[TurnRecord],
    model: str,
    sub_agent_histories: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
) -> SkillDefinition | None:
    """Analyze a single conversation for skill extraction."""
    # Skip trivial conversations (< 2 tool calls total)
    total_tool_calls = sum(t.metadata.total_tool_calls for t in turns)
    if total_tool_calls < 2:
        _console.print(Panel(
            f"[dim]Conversation [bold]{conversation_id[:8]}[/bold] — too few tool calls ({total_tool_calls})[/dim]",
            title="[yellow]Skills · Conversation · Skipped[/yellow]",
            border_style="dim yellow",
        ))
        return None

    # Check if a skill was applied — if so, try refinement first
    for turn in turns:
        if turn.metadata.skill_applied:
            existing = get_skill(turn.metadata.skill_applied)
            if existing:
                refined = await _refine_skill(existing, messages, model, options=options)
                if refined:
                    return refined

    # Build full-fidelity transcript with sub-agent internals
    transcript = _build_conversation_transcript(messages, sub_agent_histories)

    # Phase 1: Analyze the full transcript
    analysis = await _analyze_for_extraction(transcript, model, options)

    # Phase 2: Extract skill from analysis (or fall back to truncated transcript)
    if analysis:
        extraction_input = analysis
    else:
        extraction_input = transcript[:8000]

    prompt = _CONVERSATION_EXTRACTION_PROMPT.format(transcript=extraction_input)

    try:
        provider = get_provider()
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        response = await provider.chat(model=model, messages=messages, options=options or {})
        result = response.message.content or ""
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            _console.print(Panel(
                f"[dim]Conversation [bold]{conversation_id[:8]}[/bold] — no extractable skill[/dim]",
                title="[yellow]Skills · Conversation · Skipped[/yellow]",
                border_style="dim yellow",
            ))
            return None

        skill = SkillDefinition(
            id="",
            name=skill_data.get("name", ""),
            description=skill_data.get("description", ""),
            agent_scope=skill_data.get("agent_scope", "ANY"),
            trigger_patterns=skill_data.get("trigger_patterns", []),
            steps=[
                SkillStep.model_validate(s)
                for s in skill_data.get("steps", [])
            ],
            source_conversations=[conversation_id],
        )

        body = Text()
        body.append(skill.name, style="bold green")
        body.append("\n")
        body.append(skill.description, style="italic")
        body.append(f"\n{len(skill.steps)} steps", style="cyan")
        body.append(f"  from conversation {conversation_id[:8]}", style="dim")
        _console.print(Panel(
            body,
            title="[bold green]Skills · Conversation Extract[/bold green]",
            border_style="green",
        ))
        return skill
    except Exception:
        logger.exception("Failed to extract skill from conversation %s", conversation_id)
        return None


async def _analyze_sub_agent(
    agent_name: str,
    messages: list[dict[str, Any]],
    conversation_id: str,
    model: str,
    options: dict[str, Any] | None = None,
) -> SkillDefinition | None:
    """Analyze a sub-agent's conversation history for skill extraction."""
    # Count tool calls — skip trivial sub-agent runs
    tool_call_count = sum(
        1 for m in messages
        if m.get("role") == "assistant"
        for _ in (m.get("tool_calls") or [])
    )
    if tool_call_count < 2:
        return None

    # Build full-fidelity transcript
    transcript = _build_conversation_transcript(messages)

    # Phase 1: Analyze the full transcript
    analysis = await _analyze_for_extraction(transcript, model, options)

    # Phase 2: Extract skill from analysis (or fall back to truncated transcript)
    if analysis:
        extraction_input = analysis
    else:
        extraction_input = transcript[:8000]

    extraction_prompt = _get_extraction_prompt(agent_name)
    prompt = extraction_prompt.format(transcript=extraction_input)

    try:
        provider = get_provider()
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        response = await provider.chat(model=model, messages=messages, options=options or {})
        result = response.message.content or ""
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            _console.print(Panel(
                f"[dim]Sub-agent [bold]{agent_name}[/bold] — no extractable skill[/dim]",
                title="[yellow]Skills · Sub-Agent · Skipped[/yellow]",
                border_style="dim yellow",
            ))
            return None

        skill = SkillDefinition(
            id="",
            name=skill_data.get("name", ""),
            description=skill_data.get("description", ""),
            agent_scope=skill_data.get("agent_scope", "ANY"),
            trigger_patterns=skill_data.get("trigger_patterns", []),
            steps=[
                SkillStep.model_validate(s)
                for s in skill_data.get("steps", [])
            ],
            source_conversations=[conversation_id],
        )

        body = Text()
        body.append(skill.name, style="bold green")
        body.append("\n")
        body.append(skill.description, style="italic")
        body.append(f"\n{len(skill.steps)} steps", style="cyan")
        body.append(f"  from sub-agent {agent_name}", style="dim")
        _console.print(Panel(
            body,
            title="[bold green]Skills · Sub-Agent Extract[/bold green]",
            border_style="green",
        ))
        return skill
    except Exception:
        logger.exception("Failed to extract skill from sub-agent %s", agent_name)
        return None


async def _refine_skill(
    skill: SkillDefinition,
    messages: list[dict[str, Any]],
    model: str,
    options: dict[str, Any] | None = None,
) -> SkillDefinition | None:
    """Refine an existing skill based on a conversation that used it."""
    original_steps = "\n".join(
        f"  {i}. {s.tool}: {s.description}" for i, s in enumerate(skill.steps, 1)
    )
    transcript = _build_conversation_transcript(messages)

    prompt = _REFINEMENT_PROMPT.format(
        original_steps=original_steps,
        transcript=transcript,
        skill_name=skill.name,
    )

    try:
        provider = get_provider()
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        response = await provider.chat(model=model, messages=messages, options=options or {})
        result = response.message.content or ""
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            _console.print(Panel(
                f"[dim]Skill [bold]{skill.name}[/bold] — no refinement needed[/dim]",
                title="[yellow]Skills · Refine · Skipped[/yellow]",
                border_style="dim yellow",
            ))
            return None

        updated = skill.model_copy(
            update={
                "steps": [
                    SkillStep.model_validate(s)
                    for s in skill_data.get("steps", [])
                ],
                "description": skill_data.get("description", skill.description),
                "version": skill.version + 1,
            }
        )

        body = Text()
        body.append(skill.name, style="bold cyan")
        body.append(f"  v{skill.version} → v{updated.version}\n", style="dim")
        body.append(updated.description, style="italic")
        body.append(f"\n{len(updated.steps)} steps", style="cyan")
        _console.print(Panel(
            body,
            title="[bold cyan]Skills · Refined[/bold cyan]",
            border_style="cyan",
        ))
        return updated
    except Exception:
        logger.exception("Failed to refine skill '%s'", skill.name)
        return None



def _try_save_skill(skill: SkillDefinition) -> bool:
    """Try to save an extracted skill. Returns True on success."""
    try:
        existing = get_skill(skill.name)
        if existing:
            skill = skill.model_copy(
                update={
                    "source_conversations": list(
                        set(existing.source_conversations + skill.source_conversations)
                    )
                }
            )
            add_skill(skill, overwrite=True)
        else:
            add_skill(skill)
        return True
    except Exception:
        logger.exception("Failed to save extracted skill")
        return False


async def skill_extraction_loop() -> None:
    """Background loop that analyzes conversations during idle time.

    Runs as an asyncio.Task started at server boot. Sleeps between
    cycles and skips analysis when a conversation turn is active.
    """
    from sdk.turn import any_turn_active

    cfg = load_config()
    skills_cfg = getattr(cfg, "skills", None)

    if skills_cfg is None or not skills_cfg.enabled:
        logger.info("Skills extraction is disabled")
        return

    interval = skills_cfg.extraction_interval_seconds
    model = skills_cfg.extraction_model
    extraction_options = skills_cfg.extraction_options

    _console.print(Panel(
        f"interval=[bold]{interval}s[/bold]  model=[cyan]{model}[/cyan]",
        title="[bold magenta]Skills · Extraction Loop Started[/bold magenta]",
        border_style="magenta",
    ))

    while True:
        await asyncio.sleep(interval)

        # Don't compete for resources during active conversations
        if any_turn_active():
            continue

        try:
            # Get unanalyzed conversations
            unanalyzed = list_conversations(analyzed=False)
            if not unanalyzed:
                continue

            extracted_count = 0
            skipped_count = 0

            _console.print(Panel(
                f"[bold]{len(unanalyzed)}[/bold] conversations to analyze  model=[cyan]{model}[/cyan]",
                title="[bold magenta]Skills · Extraction Started[/bold magenta]",
                border_style="magenta",
            ))

            for summary in unanalyzed:
                conv_id = summary.conversation_id

                # Load full-fidelity history
                messages = load_conversation_history(conv_id)
                if messages is None:
                    # No full history saved yet — load turn records as fallback
                    mark_conversation_analyzed(conv_id)
                    skipped_count += 1
                    continue

                turns = load_conversation_turns(conv_id)
                if not turns:
                    mark_conversation_analyzed(conv_id)
                    skipped_count += 1
                    continue

                sub_histories = load_sub_agent_histories(conv_id)

                # Analyze the main conversation
                skill = await _analyze_conversation(
                    conv_id, messages, turns, model, sub_histories,
                    options=extraction_options,
                )
                if skill and skill.name:
                    if _try_save_skill(skill):
                        extracted_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1

                # Analyze each sub-agent history independently
                for sa in sub_histories:
                    sa_messages = sa.get("messages", [])
                    sa_name = sa.get("agent_name", "unknown")
                    sa_skill = await _analyze_sub_agent(
                        sa_name, sa_messages, conv_id, model,
                        options=extraction_options,
                    )
                    if sa_skill and sa_skill.name:
                        if _try_save_skill(sa_skill):
                            extracted_count += 1

                mark_conversation_analyzed(conv_id)

            body = Text()
            body.append("extracted: ", style="dim")
            body.append(str(extracted_count), style="bold green" if extracted_count else "dim")
            body.append("  skipped: ", style="dim")
            body.append(str(skipped_count), style="dim yellow" if skipped_count else "dim")
            _console.print(Panel(
                body,
                title="[bold magenta]Skills · Extraction Complete[/bold magenta]",
                border_style="magenta",
            ))


        except Exception:
            logger.exception("Error in skill extraction loop")
