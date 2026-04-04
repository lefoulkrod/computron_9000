"""Tracks base tools and dynamically loaded skills for an agent scope."""

import logging
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from ._registry import Skill, get_skill

logger = logging.getLogger(__name__)

_active_agent_state: ContextVar["AgentState | None"] = ContextVar(
    "skills_active_agent_state", default=None
)


class AgentState:
    """Tracks base tools and dynamically loaded skills.

    Holds the agent's base tools plus any skills loaded at runtime.
    Deduplicates tools by ``__name__`` and can produce a formatted
    prompt section for system message injection.
    """

    def __init__(self, base_tools: list[Callable[..., Any]]) -> None:
        self._base_tools: list[Callable[..., Any]] = list(base_tools)
        self._skills: dict[str, Skill] = {}

    def load(self, name: str) -> str | None:
        """Load a skill by name from the registry.

        Args:
            name: Skill name to load.

        Returns:
            The skill prompt on success, or None if already loaded or
            not found.
        """
        if name in self._skills:
            return None
        skill = get_skill(name)
        if skill is None:
            return None
        self._skills[name] = skill
        logger.info(
            "Loaded skill '%s' (%d tools)",
            name, len(skill.tools),
        )
        return skill.prompt

    @property
    def tools(self) -> list[Callable[..., Any]]:
        """Base tools + skill tools, deduplicated by ``__name__``."""
        seen: set[str | None] = set()
        result: list[Callable[..., Any]] = []
        for t in self._base_tools:
            fname = getattr(t, "__name__", None)
            if fname not in seen:
                result.append(t)
                seen.add(fname)
        for skill in self._skills.values():
            for t in skill.tools:
                fname = getattr(t, "__name__", None)
                if fname not in seen:
                    result.append(t)
                    seen.add(fname)
        return result

    @property
    def loaded_skill_names(self) -> frozenset[str]:
        """Names of skills that have been loaded."""
        return frozenset(self._skills)

    def build_skill_prompt(self) -> str:
        """Format loaded skill prompts for system message injection.

        Returns:
            Formatted string with all skill prompts, or empty string
            if no skills are loaded.
        """
        if not self._skills:
            return ""
        parts = [f"### {s.name}\n{s.prompt}" for s in self._skills.values()]
        return "\n── Loaded Skills ──\n\n" + "\n\n".join(parts)

    def find(self, name: str) -> Callable[..., Any] | None:
        """Look up a tool by its function name."""
        return next(
            (t for t in self.tools if getattr(t, "__name__", None) == name),
            None,
        )


def get_active_agent_state() -> "AgentState | None":
    """Return the AgentState for the current agent scope, or None."""
    return _active_agent_state.get()
