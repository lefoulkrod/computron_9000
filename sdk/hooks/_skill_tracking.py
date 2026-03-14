"""Hook that tracks skill application and updates confidence scores."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillTrackingHook:
    """Watches for apply_skill tool calls and tracks outcomes.

    When a conversation uses apply_skill, this hook records the skill name.
    Call ``record_outcome`` after the conversation ends to update the skill's
    usage counters and confidence score.
    """

    def __init__(self) -> None:
        self._applied_skill: str | None = None

    @property
    def applied_skill(self) -> str | None:
        """The name of the skill applied during this conversation, if any."""
        return self._applied_skill

    def after_tool(
        self,
        tool_name: str | None,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Detect apply_skill calls and capture the skill name."""
        if tool_name == "apply_skill" and "skill_name" in tool_arguments:
            self._applied_skill = tool_arguments["skill_name"]
            logger.info("Skill applied: %s", self._applied_skill)
        return tool_result

    def record_outcome(self, *, success: bool) -> None:
        """Update the skill registry with the usage outcome."""
        if self._applied_skill is None:
            return

        try:
            from tools.skills import record_skill_usage

            record_skill_usage(self._applied_skill, success=success)
            logger.info(
                "Recorded skill '%s' outcome: %s",
                self._applied_skill,
                "success" if success else "failure",
            )
        except Exception:
            logger.exception(
                "Failed to record outcome for skill '%s'",
                self._applied_skill,
            )
