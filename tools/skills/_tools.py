"""Agent-facing tool functions for the skills system."""

from __future__ import annotations

import json
import logging
from typing import Any

from . import _registry

logger = logging.getLogger(__name__)


def _format_skill_summary(skill: _registry.SkillDefinition) -> str:
    """Build a concise summary line for a skill."""
    confidence_pct = int(skill.confidence * 100)
    return (
        f"- {skill.name} (confidence: {confidence_pct}%, "
        f"used {skill.usage_count} times, {len(skill.steps)} steps)\n"
        f"  {skill.description}"
    )


def _fill_template(template: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Replace {param_name} placeholders in argument templates."""
    filled: dict[str, Any] = {}
    for key, value in template.items():
        if isinstance(value, str):
            for param_name, param_value in params.items():
                value = value.replace(f"{{{param_name}}}", str(param_value))
            filled[key] = value
        else:
            filled[key] = value
    return filled


async def lookup_skills(query: str) -> dict[str, object]:
    """Search for proven workflow skills by keyword.

    Returns matching skills with their name, description, confidence,
    and step count. Use apply_skill() to get the full execution plan
    for a specific skill.

    Args:
        query: Search keywords (space or comma separated). Matches against
            skill names, descriptions, trigger patterns, and categories.

    Returns:
        dict with matching skills.
    """
    try:
        skills = _registry.search_skills(query)
        if not skills:
            return {
                "status": "ok",
                "count": 0,
                "message": "No matching skills found.",
                "skills": [],
            }

        summaries = [_format_skill_summary(s) for s in skills]
        return {
            "status": "ok",
            "count": len(skills),
            "skills": "\n".join(summaries),
        }
    except Exception as exc:
        logger.exception("Failed to lookup skills")
        return {"status": "error", "message": str(exc)}


async def apply_skill(skill_name: str, parameters_json: str = "{}") -> dict[str, object]:
    """Load a skill and return a formatted execution plan with parameters filled in.

    The plan is advisory — follow the steps using your normal tools but
    adapt as needed based on actual results.

    Args:
        skill_name: Exact name of the skill to apply.
        parameters_json: JSON object mapping parameter names to values.
            Example: '{"target_url": "https://example.com", "query": "pasta recipes"}'

    Returns:
        dict with the formatted execution plan.
    """
    try:
        skill = _registry.get_skill(skill_name)
        if skill is None:
            return {
                "status": "not_found",
                "message": f"No skill named '{skill_name}'. Use lookup_skills() to search.",
            }

        if not skill.active:
            return {
                "status": "inactive",
                "message": f"Skill '{skill_name}' is inactive (confidence too low).",
            }

        # Parse parameters
        try:
            params = json.loads(parameters_json) if parameters_json else {}
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON in parameters_json."}

        # Validate required parameters
        missing = [
            p.name
            for p in skill.parameters
            if p.required and p.name not in params
        ]
        if missing:
            return {
                "status": "error",
                "message": f"Missing required parameters: {', '.join(missing)}",
                "parameters": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "type": p.type,
                        "required": p.required,
                        "example": p.example,
                    }
                    for p in skill.parameters
                ],
            }

        # Build execution plan
        confidence_pct = int(skill.confidence * 100)
        lines = [
            f"SKILL: {skill.name} (confidence: {confidence_pct}%, used {skill.usage_count} times)",
            "",
            "STEPS:",
        ]

        for i, step in enumerate(skill.steps, 1):
            filled_args = _fill_template(step.argument_template, params)
            args_str = ", ".join(f'{k}="{v}"' for k, v in filled_args.items())
            lines.append(f"{i}. {step.tool}({args_str})")
            lines.append(f"   {step.description}")
            if step.expected_outcome:
                lines.append(f"   → Expected: {step.expected_outcome}")
            if step.notes:
                lines.append(f"   Note: {step.notes}")
            lines.append("")

        if skill.preconditions:
            lines.append("PRECONDITIONS:")
            for pre in skill.preconditions:
                lines.append(f"  - {pre}")
            lines.append("")

        lines.append("Follow the plan but adapt as needed based on actual results.")

        # Emit a skill_applied event for the UI
        try:
            from sdk.events import AssistantResponse, SkillAppliedPayload, publish_event

            publish_event(
                AssistantResponse(
                    event=SkillAppliedPayload(
                        type="skill_applied",
                        skill_name=skill.name,
                        confidence=skill.confidence,
                    )
                )
            )
        except Exception:
            logger.debug("Could not publish skill_applied event")

        return {
            "status": "ok",
            "skill_name": skill.name,
            "plan": "\n".join(lines),
        }
    except Exception as exc:
        logger.exception("Failed to apply skill '%s'", skill_name)
        return {"status": "error", "message": str(exc)}
