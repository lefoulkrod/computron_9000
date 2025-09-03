"""Implementation artifact management helpers.

Stores implementation plans outside the workspace under ``settings.home_dir``
in ``implementation_plans/{workspace_name}``. No symlinks or mounts are
created; agents must access plans via tool functions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config
from tools.virtual_computer.workspace import get_current_workspace_folder

logger = logging.getLogger(__name__)


def _require_workspace() -> str:
    """Return the active workspace name or raise a ValueError.

    Returns:
        str: The current workspace name.

    Raises:
        ValueError: If no workspace has been set.
    """
    ws = get_current_workspace_folder()
    if not ws:
        msg = "No active workspace set. Call set_workspace_folder(name) first."
        raise ValueError(msg)
    return ws


def _get_implementation_plans_root() -> Path:
    """Return the absolute root directory for implementation plans.

    Location: ``settings.home_dir/implementation_plans``

    Returns:
        Path: Absolute path to the plans root directory.
    """
    cfg = config.load_config()
    return Path(cfg.settings.home_dir).expanduser().resolve() / "implementation_plans"


def _get_external_implementation_dir(workspace: str | None = None) -> Path:
    """Return the absolute directory for a workspace's external implementation files.

    Args:
        workspace: Optional explicit workspace name. Defaults to current workspace.

    Returns:
        Path: Absolute path to ``<settings.home_dir>/implementation_plans/{workspace}``.
    """
    ws = workspace or _require_workspace()
    return _get_implementation_plans_root() / ws


def _ensure_external_plan_dir(workspace: str | None = None) -> Path:
    """Ensure the external plan directory exists, and return its path.

    Args:
        workspace: Optional explicit workspace name. Defaults to current workspace.

    Returns:
        Path: Absolute path to the external plan directory.
    """
    ws = workspace or _require_workspace()
    external_dir = _get_external_implementation_dir(ws)
    external_dir.mkdir(parents=True, exist_ok=True)
    return external_dir


def save_plan_json(plan: dict[str, Any] | list[Any] | str) -> str:
    """Save the implementation plan to the external location as ``plan.json``.

    Args:
        plan: The plan content as a dict/list (will be JSON-serialized) or a JSON string.

    Returns:
        str: The absolute path to the saved plan.json file.
    """
    ws = _require_workspace()
    external_dir = _ensure_external_plan_dir(ws)
    plan_path = external_dir / "plan.json"
    try:
        if isinstance(plan, str):
            # Validate JSON but write exactly as given if valid
            json.loads(plan)
            plan_path.write_text(plan, encoding="utf-8")
        else:
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save plan.json for workspace %s", ws)
        raise
    return str(plan_path)


def _write_implementation_file(rel_path: str, content: str | bytes, *, append: bool = False) -> str:
    """Write or append to a file under the external implementation directory.

    Args:
        rel_path: Path relative to the workspace implementation dir.
        content: Text (utf-8) or bytes to write.
        append: Whether to append (True) or overwrite (False).

    Returns:
        str: Absolute path written.
    """
    ws = _require_workspace()
    base = _ensure_external_plan_dir(ws)
    target = (base / rel_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = "ab" if isinstance(content, bytes) else ("a" if append else "w")
        if isinstance(content, bytes):
            with target.open(mode) as f:  # type: ignore[arg-type]
                f.write(content)
        else:
            with target.open(mode, encoding="utf-8") as f:  # type: ignore[arg-type]
                f.write(content)
    except Exception:
        logger.exception("Failed to write implementation file %s for workspace %s", rel_path, ws)
        raise
    return str(target)


def _read_implementation_file(rel_path: str) -> str:
    """Read a UTF-8 text file from the external implementation directory.

    Args:
        rel_path: Path relative to the workspace implementation dir.

    Returns:
        str: File contents as UTF-8 text.
    """
    ws = _require_workspace()
    target = _ensure_external_plan_dir(ws) / rel_path
    try:
        return target.read_text(encoding="utf-8")
    except Exception:
        logger.exception("Failed to read implementation file %s for workspace %s", rel_path, ws)
        raise


def get_current_workspace_plan_json() -> str:
    """Tool function: Return the plan.json content for the current workspace.

    Returns:
        str: The JSON string content of ``plan.json``. Raises on errors.
    """
    ws = _require_workspace()
    external_dir = _ensure_external_plan_dir(ws)
    plan_path = external_dir / "plan.json"
    try:
        content = plan_path.read_text(encoding="utf-8")
        # Validate it's JSON; return original content (preserve formatting)
        json.loads(content)
    except Exception:
        logger.exception("Failed to retrieve plan.json for workspace %s", ws)
        raise
    else:
        return content


__all__ = [
    "get_current_workspace_plan_json",
    "save_plan_json",
]
