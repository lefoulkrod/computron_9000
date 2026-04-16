"""Autonomous task engine — persistent, background-executing goals.

Public API::

    from tasks import get_store

    store = get_store()  # lazily initialized on first call
"""

from __future__ import annotations

from tasks._executor import TaskExecutor
from tasks._file_store import GOALS_SUBDIR
from tasks._notifier import TelegramNotifier
from tasks._runner import TaskRunner
from tasks._singleton import get_store
from tasks._store import TaskStore
from tasks._tools import add_task, begin_goal, commit_goal, list_goals, list_tasks, trigger_goal

__all__ = [
    "GOALS_SUBDIR",
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
