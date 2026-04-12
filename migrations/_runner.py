"""Migration runner — discovers and applies pending migrations."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_APPLIED_FILE = ".migrations.json"

# Registry of migrations in the order they were added.
# Each entry is (name, callable). The callable receives the state directory.
_MIGRATIONS: list[tuple[str, "typing.Callable[[Path], None]"]] = []


def _register(name: str) -> "typing.Callable":
    """Decorator to register a migration function."""
    def decorator(fn: "typing.Callable[[Path], None]") -> "typing.Callable[[Path], None]":
        _MIGRATIONS.append((name, fn))
        return fn
    return decorator


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
    # Import migration modules to trigger registration
    import migrations._001_task_agent_to_profile  # noqa: F401
    import migrations._002_install_default_profiles  # noqa: F401

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


# Re-export for type checking
import typing  # noqa: E402
