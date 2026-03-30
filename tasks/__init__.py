"""Autonomous task engine — persistent, background-executing goals.

Public API::

    from tasks import init_store, get_store

    store = init_store(goals_dir)  # call once at startup
    store = get_store()            # use anywhere after init
"""

from __future__ import annotations

from pathlib import Path

from tasks._file_store import FileTaskStore
from tasks._store import TaskStore

_store: TaskStore | None = None


def init_store(goals_dir: Path) -> FileTaskStore:
    """Initialize the global task store. Call once at startup."""
    global _store  # noqa: PLW0603
    _store = FileTaskStore(goals_dir)
    return _store


def get_store() -> TaskStore:
    """Return the initialized task store.

    Raises:
        RuntimeError: If ``init_store`` has not been called yet.
    """
    if _store is None:
        msg = "TaskStore not initialized — call init_store() first"
        raise RuntimeError(msg)
    return _store


__all__ = ["TaskStore", "get_store", "init_store"]
