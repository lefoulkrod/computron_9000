"""Skill model and registry for progressive tool loading.

Built-in skills are registered lazily on first access to get_skill or
list_skills, avoiding circular imports while keeping registration
centralized.
"""

import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Skill(BaseModel):
    """A loadable bundle of tools and a prompt fragment.

    Attributes:
        name: Short identifier used in load_skill() calls.
        description: One-line description shown in the skill catalog.
        prompt: Prompt fragment injected when the skill is loaded.
        tools: Tool callables provided by this skill. Typed as ``list[Any]``
            to avoid pydantic introspecting each callable's signature at
            construction time — ``Callable[..., Any]`` triggers
            ``typing.get_type_hints`` which can deadlock on the import lock
            when skills are registered from inside an already-loading
            module (the coder/browser/goal_planner imports run during
            ``_ensure_builtins`` on the first tool-using turn).
    """

    name: str
    description: str
    prompt: str
    tools: list[Any]

    model_config = {"arbitrary_types_allowed": True}


_SKILL_REGISTRY: dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    """Register a skill in the global registry.

    Args:
        skill: The skill to register. Overwrites any existing skill with
            the same name.
    """
    if skill.name in _SKILL_REGISTRY:
        logger.warning("Overwriting existing skill '%s'", skill.name)
    _SKILL_REGISTRY[skill.name] = skill
    logger.info("Registered skill '%s' (%d tools)", skill.name, len(skill.tools))


_builtins_registered = False


def _strip_grounding_tools(skill: Skill) -> Skill:
    """Return a copy of *skill* without any local-UI-TARS grounding tools.

    These tools shell out to the local inference server; turning the
    feature off should make them invisible to the agent.
    """
    from tools.browser.vision import browser_visual_action
    from tools.desktop._tools import perform_visual_action

    blocked = {browser_visual_action, perform_visual_action}
    filtered = [t for t in skill.tools if t not in blocked]
    if len(filtered) == len(skill.tools):
        return skill
    return Skill(
        name=skill.name,
        description=skill.description,
        prompt=skill.prompt,
        tools=filtered,
    )


def _ensure_builtins() -> None:
    """Register all built-in skills on first call.

    The flag is flipped only after every built-in is registered. If the
    call is interrupted (exception, cancellation) the flag stays False
    so the next caller retries cleanly — otherwise the registry would
    be permanently empty for the life of the process.
    """
    global _builtins_registered
    if _builtins_registered:
        return

    from config import load_config
    from skills.browser import _SKILL as browser_skill
    from skills.coder import _SKILL as coder_skill
    from skills.goal_planner import _SKILL as goal_planner_skill

    features = load_config().features

    register_skill(coder_skill)
    register_skill(goal_planner_skill)
    register_skill(
        browser_skill if features.visual_grounding else _strip_grounding_tools(browser_skill)
    )

    if features.desktop:
        from skills.desktop import _SKILL as desktop_skill
        register_skill(
            desktop_skill if features.visual_grounding else _strip_grounding_tools(desktop_skill)
        )
    if features.image_generation:
        from skills.image_generation import _SKILL as image_skill
        register_skill(image_skill)
    if features.music_generation:
        from skills.music_generation import _SKILL as music_skill
        register_skill(music_skill)

    _builtins_registered = True


def get_skill(name: str) -> Skill | None:
    """Look up a skill by name."""
    _ensure_builtins()
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[tuple[str, str]]:
    """Return (name, description) pairs for all registered skills."""
    _ensure_builtins()
    return [(s.name, s.description) for s in _SKILL_REGISTRY.values()]
