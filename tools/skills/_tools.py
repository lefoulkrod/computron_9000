"""Agent-facing tool functions for the skills system."""

from __future__ import annotations

import logging

from skills import _registry

logger = logging.getLogger(__name__)


def _format_skill_summary(skill: _registry.SkillDefinition) -> str:
    """Build a concise summary line for a skill."""
    return (
        f"- {skill.name} (used {skill.usage_count} times, {len(skill.steps)} steps)\n"
        f"  {skill.description}"
    )


async def lookup_skills(query: str) -> dict[str, object]:
    """Search for proven workflow skills by keyword.

    Returns matching skills with their name, description, confidence,
    and step count. Use apply_skill() to get the full execution plan
    for a specific skill.

    Args:
        query: Search keywords (space or comma separated). Matches against
            skill names, descriptions, and trigger patterns.

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


async def apply_skill(skill_name: str) -> dict[str, object]:
    """Load a skill and return its execution plan.

    The plan is advisory — follow the steps using your normal tools,
    fill in parameters from context, and adapt as needed.

    Args:
        skill_name: Exact name of the skill to apply.

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

        # Build execution plan
        lines = [
            f"SKILL: {skill.name} (used {skill.usage_count} times)",
            f"{skill.description}",
            "",
            "STEPS:",
        ]

        for i, step in enumerate(skill.steps, 1):
            lines.append(f"{i}. [{step.tool}] {step.description}")
            if step.notes:
                lines.append(f"   Note: {step.notes}")
            lines.append("")

        lines.append("Follow the steps but adapt as needed. Fill in specifics from the user's request.")

        # Emit a skill_applied event for the UI
        try:
            from sdk.events import AssistantResponse, SkillAppliedPayload, publish_event

            publish_event(
                AssistantResponse(
                    event=SkillAppliedPayload(
                        type="skill_applied",
                        skill_name=skill.name,
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
