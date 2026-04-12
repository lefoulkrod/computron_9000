"""Autonomous task engine — persistent, background-executing goals.

Public API::

    from tasks import get_store

    store = get_store()  # lazily initialized on first call
"""

from __future__ import annotations

from pathlib import Path

from tasks._file_store import FileTaskStore
from tasks._store import TaskStore

_store: TaskStore | None = None


def get_store() -> TaskStore:
    """Return the task store, lazily initializing on first access."""
    global _store  # noqa: PLW0603
    if _store is None:
        from config import load_config

        cfg = load_config()
        goals_dir = Path(cfg.goals.goals_dir or Path(cfg.settings.home_dir) / "goals")
        _store = FileTaskStore(goals_dir, default_timezone=cfg.goals.timezone)
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
