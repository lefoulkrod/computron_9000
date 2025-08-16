"""Global management of an optional workspace folder name."""

_workspace_folder: str | None = None


def set_workspace_folder(name: str) -> None:
    """Set the name of the workspace folder for all virtual computer tools.

    Args:
        name (str): The workspace folder name (directory created under host home_dir and
            visible in the container under container_working_dir).
    """
    global _workspace_folder
    _workspace_folder = name


def get_current_workspace_folder() -> str | None:
    """Get the currently set workspace folder name, if any.

    Returns:
        str | None: The workspace folder name, or None if not set.
    """
    return _workspace_folder
