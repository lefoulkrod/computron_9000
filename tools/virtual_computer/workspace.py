"""Workspace folder management for virtual computer tools."""

from pathlib import Path

from config import load_config

_workspace_folder: str | None = None


def set_working_directory_name(name: str) -> None:
    """Set the name of the workspace for all virtual computer tools.

    Args:
        name (str): The workspace name.
    """
    global _workspace_folder
    _workspace_folder = name


def get_working_directory_name() -> str | None:
    """Get the currently set workspace name, if any.

    Returns:
        str | None: The workspace name, or None if not set.
    """
    return _workspace_folder


def get_current_working_directory() -> str:
    """Get the current working directory for the virtual computer.

    Returns:
        str: The current working directory path.
    """
    config = load_config()

    abs_path = Path(config.virtual_computer.container_working_dir) / _workspace_folder
    return str(abs_path.resolve())
