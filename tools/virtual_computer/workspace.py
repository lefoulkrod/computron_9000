"""Workspace state and implementation-plan management helpers.

This module tracks the active workspace folder name (used for scoping file
operations under the virtual computer home). Implementation artifact
management (plan storage/retrieval) lives in
``tools.virtual_computer.implementation_artifacts``.

Important: Plans are not mounted or symlinked into the workspace. Agents must
access them only via explicit tool functions.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import config
from config import AppConfig

_STATE: dict[str, str | None] = {"workspace_folder": None}

logger = logging.getLogger(__name__)


def set_workspace_folder(name: str) -> None:
    """Set the workspace folder name used by virtual computer tools.

    Args:
        name: The folder name created under the host ``home_dir`` and visible
            in the container under ``container_working_dir``.
    """
    _STATE["workspace_folder"] = name


def get_current_workspace_folder() -> str | None:
    """Return the current workspace folder name.

    Returns:
        str | None: The workspace folder name, or ``None`` if not set.
    """
    return _STATE["workspace_folder"]


def reset_workspace_folder() -> None:
    """Clear the active workspace folder name (mainly for tests)."""
    _STATE["workspace_folder"] = None


def _require_workspace() -> str:
    """Return the active workspace name or raise a ValueError.

    Returns:
        str: The current workspace name.

    Raises:
        ValueError: If no workspace has been set.
    """
    ws = _STATE["workspace_folder"]
    if not ws:
        msg = "No active workspace set. Call set_workspace_folder(name) first."
        raise ValueError(msg)
    return ws


def _load_config() -> AppConfig:
    # Importing the module at top-level keeps patchability via config.load_config
    return config.load_config()


# Thin wrappers to maintain the public API but delegate implementation to the
# new implementation_artifacts module. Use local imports to avoid circular deps.


def save_plan_json(plan: dict[str, Any] | list[Any] | str) -> str:
    """Save the implementation plan to the external location as ``plan.json``.

    Delegates to ``tools.virtual_computer.implementation_artifacts.save_plan_json``.

    Args:
        plan: The plan content as a dict/list (will be JSON-serialized) or a JSON string.

    Returns:
        str: The absolute path to the saved ``plan.json`` file.
    """
    impl = importlib.import_module("tools.virtual_computer.implementation_artifacts")
    return impl.save_plan_json(plan)


def get_current_workspace_plan_json() -> str:
    """Return the plan.json content for the current workspace.

    Delegates to
    ``tools.virtual_computer.implementation_artifacts.get_current_workspace_plan_json``.

    Returns:
        str: JSON string content of ``plan.json``.
    """
    impl = importlib.import_module("tools.virtual_computer.implementation_artifacts")
    return impl.get_current_workspace_plan_json()


# Control star-import exposure; only expose public API and tool function
__all__ = [
    "get_current_workspace_folder",
    "get_current_workspace_plan_json",
    "reset_workspace_folder",
    "save_plan_json",
    "set_workspace_folder",
]
