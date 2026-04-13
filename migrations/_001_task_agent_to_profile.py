"""Migration 001: Convert legacy task ``agent`` field to ``agent_profile``.

Legacy tasks used an ``agent`` string field (e.g. "browser", "coder",
"computron") to select which agent ran the task. This migration converts
them to the new ``agent_profile`` field that references an AgentProfile ID.

Mapping:
  - "browser"   → "research_agent"
  - "coder"     → "code_expert"
  - "computron" → "computron"

Also strips intermediate fields (``skills``, ``profile``, ``agent_config``)
that were part of a never-shipped format.

A backup of each modified goal file is saved under
``{state_dir}/.backups/001_task_agent_to_profile/goals/{goal_id}.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from migrations._backup import backup_file

logger = logging.getLogger(__name__)

# Profile IDs below must match the filenames in agents/default_profiles/
# (installed by migration 002_install_default_profiles).
_AGENT_TO_PROFILE: dict[str, str] = {
    "browser": "research_agent",
    "coder": "code_expert",
    "computron": "computron",
}

_STRIP_FIELDS = {"skills", "profile", "agent_config"}


def _migrate_task(task: dict) -> bool:
    """Migrate a single task dict in place. Returns True if modified."""
    changed = False

    # Map legacy agent → agent_profile
    if "agent" in task and "agent_profile" not in task:
        agent = task.pop("agent")
        profile_id = _AGENT_TO_PROFILE.get(agent)
        if profile_id:
            task["agent_profile"] = profile_id
        else:
            # Unknown legacy agent — default to computron
            task["agent_profile"] = "computron"
        changed = True

    # Strip intermediate/legacy fields
    for field in _STRIP_FIELDS:
        if field in task:
            task.pop(field)
            changed = True

    return changed


def migrate(state_dir: Path) -> None:
    """Migrate all goal files in the state directory."""
    goals_dir = state_dir / "goals"
    if not goals_dir.is_dir():
        logger.debug("No goals directory at %s, nothing to migrate", goals_dir)
        return

    migrated_count = 0
    for goal_path in goals_dir.glob("*.json"):
        try:
            data = json.loads(goal_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable goal file %s: %s", goal_path, exc)
            continue

        tasks = data.get("tasks", [])
        if not tasks:
            continue

        file_changed = False
        for task in tasks:
            if _migrate_task(task):
                file_changed = True

        if file_changed:
            # Back up the original before writing
            backup_path = backup_file(state_dir, "001_task_agent_to_profile", goal_path)
            logger.info("Backed up %s → %s", goal_path.name, backup_path)

            # Write migrated data
            goal_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            migrated_count += 1
            logger.info("Migrated %d task(s) in %s", len(tasks), goal_path.name)

    logger.info("Migration complete: %d goal file(s) updated", migrated_count)
