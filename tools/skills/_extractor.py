"""Background skill extraction loop.

Analyzes stored conversations during idle time to discover repeatable
patterns and extract them as reusable skills.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from config import load_config
from tools.conversations import (
    ConversationRecord,
    list_conversations,
    load_conversation,
    mark_analyzed,
)

from ._models import SkillDefinition, SkillParameter, SkillStep
from ._registry import add_skill, get_skill, list_skills, save_registry

logger = logging.getLogger(__name__)

# Extraction prompt for single conversation
_SINGLE_EXTRACTION_PROMPT = """\
This conversation successfully completed a task. Could this workflow be
generalized into a reusable skill? If yes, extract it as a JSON object
matching this schema. If the task is too specific or one-off, reply with
just the word NO.

User request: "{user_message}"

Tool call sequence:
{tool_sequence}

Final outcome: {outcome}

Required JSON schema for skill extraction:
{{
  "name": "snake_case_skill_name",
  "description": "What the skill accomplishes",
  "agent_scope": "COMPUTRON_9000 | BROWSER_AGENT | COMPUTER_AGENT | ANY",
  "trigger_patterns": ["natural language descriptions of when to use this"],
  "category": "web_scraping | code_generation | data_processing | file_management | research | other",
  "parameters": [
    {{"name": "param_name", "description": "what it is", "type": "string", "required": true, "example": "example_value"}}
  ],
  "preconditions": ["any requirements"],
  "steps": [
    {{
      "description": "What this step does",
      "tool": "tool_function_name",
      "argument_template": {{"arg_name": "value with {{param_name}} placeholders"}},
      "expected_outcome": "What should happen",
      "notes": "Tips or gotchas"
    }}
  ]
}}

Reply with ONLY the JSON object or the word NO. No explanation."""

# Extraction prompt for pattern clustering (2+ conversations)
_CLUSTER_EXTRACTION_PROMPT = """\
These {count} conversations all completed similar tasks successfully.
Extract the common workflow as a reusable skill.

Conversations:
{conversations}

Required JSON schema (same as single extraction above):
{{
  "name": "snake_case_skill_name",
  "description": "What the skill accomplishes",
  "agent_scope": "COMPUTRON_9000 | BROWSER_AGENT | COMPUTER_AGENT | ANY",
  "trigger_patterns": ["natural language descriptions of when to use this"],
  "category": "category_name",
  "parameters": [
    {{"name": "param_name", "description": "what it is", "type": "string", "required": true, "example": "example_value"}}
  ],
  "preconditions": ["any requirements"],
  "steps": [
    {{
      "description": "What this step does",
      "tool": "tool_function_name",
      "argument_template": {{"arg_name": "value with {{param_name}} placeholders"}},
      "expected_outcome": "What should happen",
      "notes": ""
    }}
  ]
}}

Reply with ONLY the JSON object."""

# Refinement prompt for existing skills used in new conversations
_REFINEMENT_PROMPT = """\
This skill was applied but the agent adapted it. Should the skill be updated
to reflect the actual successful workflow?

Original skill steps:
{original_steps}

Actual steps taken:
{actual_steps}

Output the updated skill JSON or just the word NO.

Required JSON schema:
{{
  "name": "{skill_name}",
  "description": "Updated description",
  "steps": [
    {{
      "description": "What this step does",
      "tool": "tool_function_name",
      "argument_template": {{}},
      "expected_outcome": "What should happen",
      "notes": ""
    }}
  ]
}}

Reply with ONLY the JSON object or the word NO."""


def _extract_tool_sequence(record: ConversationRecord) -> str:
    """Build a human-readable tool call sequence from a conversation."""
    lines = []
    for turn in record.turns:
        if turn.role == "tool" and turn.tool_calls:
            for tc in turn.tool_calls:
                args_summary = ", ".join(
                    f"{k}={repr(v)[:80]}" for k, v in tc.arguments.items()
                )
                status = "OK" if tc.success else "FAILED"
                lines.append(
                    f"  [{turn.agent_name or record.agent}] "
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


def _group_similar_conversations(
    records: list[ConversationRecord],
    threshold: float = 0.3,
) -> list[list[ConversationRecord]]:
    """Group conversations by user_message similarity."""
    groups: list[list[ConversationRecord]] = []
    assigned: set[str] = set()

    for i, rec_a in enumerate(records):
        if rec_a.id in assigned:
            continue
        group = [rec_a]
        assigned.add(rec_a.id)

        for rec_b in records[i + 1 :]:
            if rec_b.id in assigned:
                continue
            sim = _keyword_similarity(rec_a.user_message, rec_b.user_message)
            if sim >= threshold:
                group.append(rec_b)
                assigned.add(rec_b.id)

        groups.append(group)

    return groups


def _parse_skill_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from LLM output."""
    text = text.strip()
    if text.upper() == "NO":
        return None

    # Try to find JSON in the response
    # Look for { ... } block
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


async def _extract_from_single(
    record: ConversationRecord,
    model: str,
) -> SkillDefinition | None:
    """Try to extract a skill from a single successful conversation."""
    from models.generate_completion import generate_completion

    tool_sequence = _extract_tool_sequence(record)
    prompt = _SINGLE_EXTRACTION_PROMPT.format(
        user_message=record.user_message[:500],
        tool_sequence=tool_sequence[:2000],
        outcome=record.metadata.outcome,
    )

    try:
        result, _ = await generate_completion(prompt, model)
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            return None

        # Build SkillDefinition from extracted data
        return SkillDefinition(
            id="",  # Will be assigned by add_skill
            name=skill_data.get("name", ""),
            description=skill_data.get("description", ""),
            agent_scope=skill_data.get("agent_scope", "ANY"),
            trigger_patterns=skill_data.get("trigger_patterns", []),
            category=skill_data.get("category", "other"),
            parameters=[
                SkillParameter.model_validate(p)
                for p in skill_data.get("parameters", [])
            ],
            preconditions=skill_data.get("preconditions", []),
            steps=[
                SkillStep.model_validate(s)
                for s in skill_data.get("steps", [])
            ],
            confidence=0.3,  # Lower confidence for single-conversation extraction
            source_conversations=[record.id],
        )
    except Exception:
        logger.exception("Failed to extract skill from conversation %s", record.id)
        return None


async def _extract_from_cluster(
    records: list[ConversationRecord],
    model: str,
) -> SkillDefinition | None:
    """Extract a skill from a cluster of similar conversations."""
    from models.generate_completion import generate_completion

    conversations_text = ""
    for i, rec in enumerate(records[:3], 1):  # Limit to 3 to avoid token overflow
        tool_seq = _extract_tool_sequence(rec)
        conversations_text += (
            f"\n--- Conversation {i} ---\n"
            f"User: {rec.user_message[:300]}\n"
            f"Tools: {tool_seq[:1000]}\n"
            f"Outcome: {rec.metadata.outcome}\n"
        )

    prompt = _CLUSTER_EXTRACTION_PROMPT.format(
        count=len(records),
        conversations=conversations_text,
    )

    try:
        result, _ = await generate_completion(prompt, model)
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            return None

        return SkillDefinition(
            id="",
            name=skill_data.get("name", ""),
            description=skill_data.get("description", ""),
            agent_scope=skill_data.get("agent_scope", "ANY"),
            trigger_patterns=skill_data.get("trigger_patterns", []),
            category=skill_data.get("category", "other"),
            parameters=[
                SkillParameter.model_validate(p)
                for p in skill_data.get("parameters", [])
            ],
            preconditions=skill_data.get("preconditions", []),
            steps=[
                SkillStep.model_validate(s)
                for s in skill_data.get("steps", [])
            ],
            confidence=0.5,  # Higher confidence for cluster extraction
            source_conversations=[r.id for r in records],
        )
    except Exception:
        logger.exception("Failed to extract skill from conversation cluster")
        return None


async def _refine_skill(
    skill: SkillDefinition,
    record: ConversationRecord,
    model: str,
) -> SkillDefinition | None:
    """Refine an existing skill based on a new successful conversation that used it."""
    from models.generate_completion import generate_completion

    original_steps = "\n".join(
        f"  {i}. {s.tool}: {s.description}" for i, s in enumerate(skill.steps, 1)
    )
    actual_steps = _extract_tool_sequence(record)

    prompt = _REFINEMENT_PROMPT.format(
        original_steps=original_steps,
        actual_steps=actual_steps[:2000],
        skill_name=skill.name,
    )

    try:
        result, _ = await generate_completion(prompt, model)
        skill_data = _parse_skill_json(result)
        if skill_data is None:
            return None

        # Update only the steps and description if they changed
        updated = skill.model_copy(
            update={
                "steps": [
                    SkillStep.model_validate(s)
                    for s in skill_data.get("steps", [])
                ],
                "description": skill_data.get("description", skill.description),
                "version": skill.version + 1,
                "source_conversations": list(
                    set(skill.source_conversations + [record.id])
                ),
            }
        )
        return updated
    except Exception:
        logger.exception("Failed to refine skill '%s'", skill.name)
        return None


def _apply_skill_decay(decay_days: int) -> None:
    """Reduce confidence for skills not used within the decay period."""
    cutoff = (datetime.now(UTC) - timedelta(days=decay_days)).isoformat()
    skills = list_skills(active_only=False)
    changed = False

    for skill in skills:
        if not skill.active:
            continue
        if skill.last_used_at and skill.last_used_at < cutoff:
            skill.confidence = max(0.0, skill.confidence - 0.1)
            if skill.confidence < 0.1:
                skill.active = False
                logger.info("Archived skill '%s' due to decay", skill.name)
            changed = True

    if changed:
        save_registry(skills)


async def _analyze_conversations(
    records: list[ConversationRecord],
    model: str,
    *,
    single_extraction: bool = True,
) -> None:
    """Analyze a batch of unanalyzed conversations for skill extraction."""
    # Strategy 3: Refinement — check if any used an existing skill
    for record in records:
        if record.metadata.skill_applied and record.metadata.outcome == "success":
            existing = get_skill(record.metadata.skill_applied)
            if existing:
                refined = await _refine_skill(existing, record, model)
                if refined:
                    try:
                        add_skill(refined, overwrite=True)
                        logger.info("Refined skill '%s' (v%d)", refined.name, refined.version)
                    except Exception:
                        logger.exception("Failed to save refined skill")
                mark_analyzed(record.id)

    # Filter to remaining unanalyzed successful conversations
    successful = [
        r for r in records
        if r.metadata.outcome == "success" and not r.metadata.analyzed
    ]
    if not successful:
        return

    # Strategy 1: Pattern clustering (2+ similar conversations)
    groups = _group_similar_conversations(successful)
    for group in groups:
        if len(group) >= 2:
            skill = await _extract_from_cluster(group, model)
            if skill and skill.name:
                try:
                    existing = get_skill(skill.name)
                    if existing:
                        # Merge source conversations
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
                    logger.info("Extracted cluster skill '%s'", skill.name)
                except Exception:
                    logger.exception("Failed to save extracted skill")
            for rec in group:
                mark_analyzed(rec.id)

    # Strategy 2: Single conversation extraction
    if single_extraction:
        for record in successful:
            if record.metadata.analyzed:
                continue
            skill = await _extract_from_single(record, model)
            if skill and skill.name:
                try:
                    if not get_skill(skill.name):
                        add_skill(skill)
                        logger.info("Extracted single-conversation skill '%s'", skill.name)
                except Exception:
                    logger.exception("Failed to save extracted skill")
            mark_analyzed(record.id)


async def skill_extraction_loop() -> None:
    """Background loop that analyzes conversations during idle time.

    Runs as an asyncio.Task started at server boot. Sleeps between
    cycles and skips analysis when a conversation turn is active.
    """
    from sdk.loop import is_turn_active

    cfg = load_config()
    skills_cfg = getattr(cfg, "skills", None)

    if skills_cfg is None or not skills_cfg.enabled:
        logger.info("Skills extraction is disabled")
        return

    interval = skills_cfg.extraction_interval_seconds
    model = skills_cfg.extraction_model
    single_extraction = skills_cfg.single_conversation_extraction
    decay_days = skills_cfg.decay_days

    logger.info(
        "Starting skill extraction loop (interval=%ds, model=%s)",
        interval,
        model,
    )

    while True:
        await asyncio.sleep(interval)

        # Don't compete for resources during active conversations
        if is_turn_active():
            continue

        try:
            # Get unanalyzed conversations
            unanalyzed = list_conversations(analyzed=False, limit=20)
            if not unanalyzed:
                # Apply decay even if nothing to analyze
                _apply_skill_decay(decay_days)
                continue

            # Load full records
            records = []
            for entry in unanalyzed:
                rec = load_conversation(entry.id)
                if rec:
                    records.append(rec)

            if records:
                await _analyze_conversations(
                    records,
                    model,
                    single_extraction=single_extraction,
                )

            # Apply decay
            _apply_skill_decay(decay_days)

        except Exception:
            logger.exception("Error in skill extraction loop")
