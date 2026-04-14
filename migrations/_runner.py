"""Migration runner — applies pending migrations in a fixed order."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from migrations._001_task_agent_to_profile import migrate as _001_task_agent_to_profile
from migrations._002_install_default_profiles import migrate as _002_install_default_profiles

logger = logging.getLogger(__name__)

_APPLIED_FILE = ".migrations.json"

# Migrations run top-to-bottom on first startup; already-applied entries are
# skipped on subsequent runs. Insert new migrations at the bottom — the order
# must stay stable across releases.
_MIGRATIONS: list[tuple[str, Callable[[Path], None]]] = [
    ("001_task_agent_to_profile", _001_task_agent_to_profile),
    ("002_install_default_profiles", _002_install_default_profiles),
]


def _load_applied(state_dir: Path) -> set[str]:
    path = state_dir / _APPLIED_FILE
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt %s, treating as empty", path)
        return set()


def _save_applied(state_dir: Path, applied: set[str]) -> None:
    path = state_dir / _APPLIED_FILE
    path.write_text(json.dumps(sorted(applied), indent=2), encoding="utf-8")


def run_migrations(state_dir: Path) -> None:
    """Run all pending migrations against the state directory."""
    state_dir = Path(state_dir)
    if not state_dir.is_dir():
        logger.debug("State directory %s does not exist, skipping migrations", state_dir)
        return

    applied = _load_applied(state_dir)
    pending = [(name, fn) for name, fn in _MIGRATIONS if name not in applied]

    if not pending:
        return

    logger.info("%d pending migration(s)", len(pending))
    for name, fn in pending:
        logger.info("Running migration: %s", name)
        fn(state_dir)
        applied.add(name)
        _save_applied(state_dir, applied)
        logger.info("Migration complete: %s", name)
