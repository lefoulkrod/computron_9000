"""Path resolution and sanitization helpers for virtual computer workspace."""

from __future__ import annotations

import logging
from pathlib import Path

from tools.virtual_computer.workspace import get_current_workspace_folder

logger = logging.getLogger(__name__)


def resolve_under_home(path: str) -> tuple[Path, Path, str]:
    """Resolve a relative/absolute path inside the virtual computer home.

    Args:
        path: Input path provided by caller; may be absolute, relative, or
            include the container working directory prefix.

    Returns:
        Tuple of (absolute_path, home_dir, relative_path_string) where
        relative_path_string is the path relative to the virtual computer
        home (optionally including the active workspace prefix).
    """
    # Local import so tests patching config.load_config see effect without needing
    # to reload this module; keeps backward-compatible monkeypatch behavior.
    from config import load_config  # Local import to allow test monkeypatching

    config = load_config()
    home_dir = Path(config.virtual_computer.home_dir).resolve()
    workspace = get_current_workspace_folder()
    container_working_dir = str(
        getattr(
            config.virtual_computer,
            "container_working_dir",
            "/home/computron",
        )
    ).rstrip("/")
    input_path = Path(path)
    if input_path.is_absolute():
        input_path = input_path.relative_to(input_path.anchor)
    container_rel = Path(container_working_dir).relative_to(Path(container_working_dir).anchor)
    input_parts = list(input_path.parts)
    container_parts = list(container_rel.parts)
    cleaned = input_path
    if tuple(input_parts[: len(container_parts)]) == tuple(container_parts):
        remainder = Path(*input_parts[len(container_parts) :])
        if workspace and remainder.parts and remainder.parts[0] == workspace:
            remainder = Path(*remainder.parts[1:])
        cleaned = remainder
    else:
        cleaned = input_path
    parts = []
    for part in cleaned.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    safe_rel = Path(*parts) if parts else Path()
    rel_path = Path(workspace) / safe_rel if workspace else safe_rel
    abs_path = (home_dir / rel_path).resolve()
    rel_return_path = str(rel_path)
    return abs_path, home_dir, rel_return_path
