"""Skill model and registry for progressive tool loading.

Built-in skills are registered lazily on first access to get_skill or
list_skills, avoiding circular imports while keeping registration
centralized.
"""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Skill(BaseModel):
    """A loadable bundle of tools and a prompt fragment.

    Attributes:
        name: Short identifier used in load_skill() calls.
        description: One-line description shown in the skill catalog.
        prompt: Prompt fragment injected when the skill is loaded.
        tools: Tool callables provided by this skill.
    """

    name: str
    description: str
    prompt: str
    tools: list[Callable[..., Any]]

    model_config = {"arbitrary_types_allowed": True}


_SKILL_REGISTRY: dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    """Register a skill in the global registry.

    Args:
        skill: The skill to register. Overwrites any existing skill with
            the same name.
    """
    _ensure_builtins()
    if skill.name in _SKILL_REGISTRY:
        logger.warning("Overwriting existing skill '%s'", skill.name)
    _SKILL_REGISTRY[skill.name] = skill
    logger.info("Registered skill '%s' (%d tools)", skill.name, len(skill.tools))


_builtins_registered = False


def _ensure_builtins() -> None:
    """Register all built-in skills on first call."""
    global _builtins_registered
    if _builtins_registered:
        return
    _builtins_registered = True

    from config import load_config

    from skills.browser import _SKILL as browser_skill
    from skills.coder import _SKILL as coder_skill
    from skills.desktop import _SKILL as desktop_skill

    for skill in (browser_skill, coder_skill, desktop_skill):
        register_skill(skill)

    features = load_config().features
    if features.image_generation:
        from skills.image_generation import _SKILL as image_skill
        register_skill(image_skill)
    if features.music_generation:
        from skills.music_generation import _SKILL as music_skill
        register_skill(music_skill)


def get_skill(name: str) -> Skill | None:
    """Look up a skill by name."""
    _ensure_builtins()
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[tuple[str, str]]:
    """Return (name, description) pairs for all registered skills."""
    _ensure_builtins()
    return [(s.name, s.description) for s in _SKILL_REGISTRY.values()]
