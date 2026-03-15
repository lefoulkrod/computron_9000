"""Persistence layer for skill definitions."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import load_config

from ._models import SkillDefinition

logger = logging.getLogger(__name__)


def _get_registry_path() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "skills" / "registry.json"


def load_registry() -> list[SkillDefinition]:
    """Read and parse the skills registry. Returns empty list if missing."""
    path = _get_registry_path()
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return [SkillDefinition.model_validate(entry) for entry in data]
    except Exception:
        logger.exception("Failed to load skills registry from %s", path)
        return []


def save_registry(skills: list[SkillDefinition]) -> None:
    """Atomically write the skills registry."""
    path = _get_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    serialized = [s.model_dump() for s in skills]
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(path)


def add_skill(
    definition: SkillDefinition,
    *,
    overwrite: bool = False,
) -> SkillDefinition:
    """Add or replace a skill definition in the registry."""
    skills = load_registry()
    now = datetime.now(UTC).isoformat()

    existing_idx = next(
        (i for i, s in enumerate(skills) if s.name == definition.name),
        None,
    )

    if existing_idx is not None:
        if not overwrite:
            msg = f"A skill named '{definition.name}' already exists. Pass overwrite=True to replace it."
            raise ValueError(msg)
        existing = skills[existing_idx]
        definition = definition.model_copy(
            update={
                "id": existing.id,
                "created_at": existing.created_at,
                "updated_at": now,
                "usage_count": existing.usage_count,
                "last_used_at": existing.last_used_at,
            }
        )
        skills[existing_idx] = definition
    else:
        definition = definition.model_copy(
            update={
                "id": str(uuid.uuid4()),
                "created_at": now,
                "updated_at": now,
            }
        )
        skills.append(definition)

    save_registry(skills)
    return definition


def get_skill(name: str) -> SkillDefinition | None:
    """Look up a skill by exact name."""
    return next((s for s in load_registry() if s.name == name), None)


def search_skills(
    query: str,
    *,
    agent_scope: str | None = None,
) -> list[SkillDefinition]:
    """Search skills by keyword across name, description, and trigger_patterns."""
    keywords = [k for k in re.split(r"[,\s]+", query.lower()) if k]
    if not keywords:
        return []

    results = []
    for skill in load_registry():
        if agent_scope and skill.agent_scope not in (agent_scope, "ANY"):
            continue

        haystack = " ".join([
            skill.name,
            skill.description,
            *skill.trigger_patterns,
        ]).lower()

        if any(k in haystack for k in keywords):
            results.append(skill)

    return results


def list_skills() -> list[SkillDefinition]:
    """Return all skill definitions."""
    return load_registry()


def delete_skill(name: str) -> bool:
    """Delete a skill by name. Returns True if found."""
    skills = load_registry()
    idx = next((i for i, s in enumerate(skills) if s.name == name), None)
    if idx is None:
        return False
    skills.pop(idx)
    save_registry(skills)
    return True


def record_skill_used(name: str) -> None:
    """Bump usage_count and last_used_at for a skill."""
    skills = load_registry()
    for skill in skills:
        if skill.name == name:
            skill.usage_count += 1
            skill.last_used_at = datetime.now(UTC).isoformat()
            save_registry(skills)
            return
    logger.warning("Skill '%s' not found for usage recording", name)


__all__ = [
    "SkillDefinition",
    "add_skill",
    "delete_skill",
    "get_skill",
    "list_skills",
    "load_registry",
    "record_skill_used",
    "save_registry",
    "search_skills",
]
