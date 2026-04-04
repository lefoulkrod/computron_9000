"""Agent registry mapping user-facing IDs to agent configurations."""

from agents.browser import (
    DESCRIPTION as _BROWSER_DESCRIPTION,
    NAME as _BROWSER_NAME,
    SYSTEM_PROMPT as _BROWSER_PROMPT,
    TOOLS as _BROWSER_TOOLS,
)
from agents.coding import (
    DESCRIPTION as _CODER_DESCRIPTION,
    NAME as _CODER_NAME,
    SYSTEM_PROMPT as _CODER_PROMPT,
    TOOLS as _CODER_TOOLS,
)
from agents.computron import (
    DESCRIPTION as _COMPUTRON_DESCRIPTION,
    NAME as _COMPUTRON_NAME,
    SYSTEM_PROMPT as _COMPUTRON_PROMPT,
    TOOLS as _COMPUTRON_TOOLS,
)
from agents.desktop import (
    DESCRIPTION as _DESKTOP_DESCRIPTION,
    NAME as _DESKTOP_NAME,
    SYSTEM_PROMPT as _DESKTOP_PROMPT,
    TOOLS as _DESKTOP_TOOLS,
)
from agents.computron_skills import (
    DESCRIPTION as _SKILLS_DESCRIPTION,
    NAME as _SKILLS_NAME,
    SYSTEM_PROMPT as _SKILLS_PROMPT,
    TOOLS as _SKILLS_TOOLS,
)
from agents.goal_planner import (
    DESCRIPTION as _PLANNER_DESCRIPTION,
    NAME as _PLANNER_NAME,
    SYSTEM_PROMPT as _PLANNER_PROMPT,
    TOOLS as _PLANNER_TOOLS,
)

_AGENT_REGISTRY: dict[str, tuple[str, str, str, list]] = {
    "computron": (_COMPUTRON_NAME, _COMPUTRON_DESCRIPTION, _COMPUTRON_PROMPT, _COMPUTRON_TOOLS),
    "browser": (_BROWSER_NAME, _BROWSER_DESCRIPTION, _BROWSER_PROMPT, _BROWSER_TOOLS),
    "coder": (_CODER_NAME, _CODER_DESCRIPTION, _CODER_PROMPT, _CODER_TOOLS),
    "desktop": (_DESKTOP_NAME, _DESKTOP_DESCRIPTION, _DESKTOP_PROMPT, _DESKTOP_TOOLS),
    "computron_skills": (_SKILLS_NAME, _SKILLS_DESCRIPTION, _SKILLS_PROMPT, _SKILLS_TOOLS),
    "goal_planner": (_PLANNER_NAME, _PLANNER_DESCRIPTION, _PLANNER_PROMPT, _PLANNER_TOOLS),
}

# Aliases for convenience (e.g. "computer" -> "coder")
_AGENT_ALIASES: dict[str, str] = {
    "computer": "coder",
}

AVAILABLE_AGENTS = sorted(_AGENT_REGISTRY.keys())


def resolve_agent(agent_id: str | None) -> tuple[str, str, str, list]:
    """Resolve an agent ID to its config tuple, defaulting to computron."""
    if not agent_id:
        return _AGENT_REGISTRY["computron"]
    key = _AGENT_ALIASES.get(agent_id, agent_id)
    return _AGENT_REGISTRY.get(key, _AGENT_REGISTRY["computron"])


__all__ = ["AVAILABLE_AGENTS", "resolve_agent"]
