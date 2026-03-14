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

# Auto-deactivate skills with confidence below this after min_uses.
_MIN_CONFIDENCE = 0.15
_MIN_USES_FOR_DEACTIVATE = 5


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
                # Preserve usage stats on overwrite
                "usage_count": existing.usage_count,
                "success_count": existing.success_count,
                "failure_count": existing.failure_count,
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
    active_only: bool = True,
) -> list[SkillDefinition]:
    """Search skills by keyword across name, description, trigger_patterns, and category.

    Optionally filter by agent scope.
    """
    keywords = [k for k in re.split(r"[,\s]+", query.lower()) if k]
    if not keywords:
        return []

    results = []
    for skill in load_registry():
        if active_only and not skill.active:
            continue
        if agent_scope and skill.agent_scope not in (agent_scope, "ANY"):
            continue

        haystack = " ".join([
            skill.name,
            skill.description,
            skill.category,
            *skill.trigger_patterns,
        ]).lower()

        if any(k in haystack for k in keywords):
            results.append(skill)

    return results


def list_skills(*, active_only: bool = True) -> list[SkillDefinition]:
    """Return all skill definitions, optionally filtered to active only."""
    skills = load_registry()
    if active_only:
        return [s for s in skills if s.active]
    return skills


def delete_skill(name: str) -> bool:
    """Delete a skill by name. Returns True if found."""
    skills = load_registry()
    idx = next((i for i, s in enumerate(skills) if s.name == name), None)
    if idx is None:
        return False
    skills.pop(idx)
    save_registry(skills)
    return True


def toggle_skill(name: str, *, active: bool) -> bool:
    """Toggle a skill's active state. Returns True if found."""
    skills = load_registry()
    for skill in skills:
        if skill.name == name:
            skill.active = active
            save_registry(skills)
            return True
    return False


def record_skill_usage(
    name: str,
    *,
    success: bool,
) -> None:
    """Update usage and success/failure counters for a skill."""
    skills = load_registry()
    for skill in skills:
        if skill.name == name:
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            else:
                skill.failure_count += 1
            skill.last_used_at = datetime.now(UTC).isoformat()
            skill.confidence = skill.success_count / max(skill.usage_count, 1)

            # Auto-deactivate low-confidence skills
            if (
                skill.usage_count >= _MIN_USES_FOR_DEACTIVATE
                and skill.confidence < _MIN_CONFIDENCE
            ):
                skill.active = False
                logger.info(
                    "Auto-deactivated skill '%s' (confidence %.2f after %d uses)",
                    name,
                    skill.confidence,
                    skill.usage_count,
                )

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
    "record_skill_usage",
    "save_registry",
    "search_skills",
    "toggle_skill",
]
