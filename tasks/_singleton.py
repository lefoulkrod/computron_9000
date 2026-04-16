"""Process-wide ``TaskStore`` singleton.

Lives in its own module so that both ``tasks.__init__`` (the package facade)
and ``tasks._tools`` (an internal module) can import ``get_store`` without
creating a circular import through the package root.
"""

from __future__ import annotations

from pathlib import Path

from config import load_config
from tasks._file_store import GOALS_SUBDIR, FileTaskStore
from tasks._store import TaskStore

_store: TaskStore | None = None


def get_store() -> TaskStore:
    """Return the task store, lazily initializing on first access."""
    global _store
    if _store is None:
        cfg = load_config()
        goals_dir = Path(cfg.goals.goals_dir or Path(cfg.settings.home_dir) / GOALS_SUBDIR)
        _store = FileTaskStore(goals_dir, default_timezone=cfg.goals.timezone)
    return _store
