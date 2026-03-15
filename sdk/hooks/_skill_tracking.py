"""Hook that tracks skill application and records usage."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SkillTrackingHook:
    """Watches for apply_skill tool calls and records usage."""

    def __init__(self) -> None:
        self._applied_skill: str | None = None

    @property
    def applied_skill(self) -> str | None:
        """The name of the skill applied during this turn, if any."""
        return self._applied_skill

    def after_tool(
        self,
        tool_name: str | None,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Detect apply_skill calls, capture the skill name, and bump usage."""
        if tool_name == "apply_skill" and "skill_name" in tool_arguments:
            self._applied_skill = tool_arguments["skill_name"]
            logger.info("Skill applied: %s", self._applied_skill)
            try:
                from skills import record_skill_used

                record_skill_used(self._applied_skill)
            except Exception:
                logger.exception("Failed to record usage for skill '%s'", self._applied_skill)
        return tool_result
