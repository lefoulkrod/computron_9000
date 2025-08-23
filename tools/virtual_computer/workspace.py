"""Global management of an optional workspace folder name."""

_workspace_folder: str | None = None


def set_workspace_folder(name: str) -> None:
    """Set the workspace folder name used by virtual computer tools.

    Args:
        name: The folder name created under the host ``home_dir`` and visible
            in the container under ``container_working_dir``.
    """
    global _workspace_folder
    _workspace_folder = name


def get_current_workspace_folder() -> str | None:
    """Return the current workspace folder name.

    Returns:
        str | None: The workspace folder name, or None if not set.
    """
    return _workspace_folder
