"""Agent registry mapping user-facing IDs to agent configurations."""

from agents.computron import (
    DESCRIPTION as _COMPUTRON_DESCRIPTION,
    NAME as _COMPUTRON_NAME,
    SYSTEM_PROMPT as _COMPUTRON_PROMPT,
    TOOLS as _COMPUTRON_TOOLS,
)

_AGENT_REGISTRY: dict[str, tuple[str, str, str, list]] = {
    "computron": (_COMPUTRON_NAME, _COMPUTRON_DESCRIPTION, _COMPUTRON_PROMPT, _COMPUTRON_TOOLS),
}

AVAILABLE_AGENTS = sorted(_AGENT_REGISTRY.keys())


def resolve_agent(agent_id: str | None) -> tuple[str, str, str, list]:
    """Resolve an agent ID to its config tuple, defaulting to computron."""
    return _AGENT_REGISTRY["computron"]


__all__ = ["AVAILABLE_AGENTS", "resolve_agent"]
