"""Shared formatting helpers for the iCloud Drive (rclone-backed) tools."""

from __future__ import annotations


def human_bytes(n: int) -> str:
    """Render a byte count as a short human-readable string (e.g. ``1.5 GB``)."""
    if n <= 0:
        return "0 B"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024.0
    return f"{size:.1f} PB"


def split_remote_arg(value: str) -> tuple[bool, str]:
    """Interpret a copy/move path argument.

    Returns ``(is_remote, path)``. A value beginning with ``remote:`` (or
    ``remote/``) is a remote path with the marker stripped; anything else is a
    local filesystem path returned unchanged.
    """
    if value.startswith("remote:"):
        return True, value[len("remote:"):].lstrip("/")
    if value.startswith("remote/"):
        return True, value[len("remote/"):]
    return False, value
