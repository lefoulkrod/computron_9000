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


def init_store(goals_dir: Path, default_timezone: str = "UTC") -> FileTaskStore:
    """Initialize the global task store. Call once at startup."""
    global _store  # noqa: PLW0603
    _store = FileTaskStore(goals_dir, default_timezone=default_timezone)
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


from tasks._tools import add_task, begin_goal, commit_goal, list_goals, list_tasks, trigger_goal

__all__ = [
    "TaskExecutor",
    "TaskRunner",
    "TaskStore",
    "TelegramNotifier",
    "add_task",
    "begin_goal",
    "commit_goal",
    "get_store",
    "init_store",
    "list_goals",
    "list_tasks",
    "trigger_goal",
]


def __getattr__(name: str) -> object:
    """Lazy imports for heavy classes with third-party deps."""
    if name == "TaskExecutor":
        from tasks._executor import TaskExecutor
        return TaskExecutor
    if name == "TaskRunner":
        from tasks._runner import TaskRunner
        return TaskRunner
    if name == "TelegramNotifier":
        from tasks._notifier import TelegramNotifier
        return TelegramNotifier
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
