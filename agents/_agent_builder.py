"""Build Agent instances from AgentProfile configs."""

from collections.abc import Callable
from typing import Any

from agents._agent_profiles import AgentProfile
from agents.types import Agent


def build_agent(
    profile: AgentProfile,
    tools: list[Callable[..., Any]],
    *,
    name: str | None = None,
) -> Agent:
    """Construct an Agent from a profile and tool list.

    Args:
        profile: Source profile for model/instruction/inference settings.
        tools: Tool callables the agent can invoke.
        name: Override the Agent name (defaults to the profile name upcased).

    Raises:
        RuntimeError: If the profile has no model configured.
    """
    if not profile.model:
        msg = f"Profile '{profile.id}' has no model configured — run setup wizard"
        raise RuntimeError(msg)

    raw_options: dict[str, Any] = {
        "num_ctx": profile.num_ctx,
        "num_predict": profile.num_predict,
        "temperature": profile.temperature,
        "top_k": profile.top_k,
        "top_p": profile.top_p,
        "repeat_penalty": profile.repeat_penalty,
    }
    options = {k: v for k, v in raw_options.items() if v is not None}

    return Agent(
        name=name or profile.name.upper(),
        description=profile.description,
        instruction=profile.system_prompt,
        tools=tools,
        model=profile.model,
        think=profile.think or False,
        options=options,
        max_iterations=profile.max_iterations or 0,
    )


__all__ = ["build_agent"]
