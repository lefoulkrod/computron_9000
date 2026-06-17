"""Shared formatting helpers for the unified Drive tools."""

from __future__ import annotations

from typing import Any


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


def format_entry(entry: dict[str, Any]) -> str:
    """One-line render of a directory entry returned by ``drive_list``."""
    name = entry.get("name", "?")
    handle = entry.get("handle", "")
    if entry.get("is_dir"):
        return f"- [dir]  {name}/  [{handle}]"
    size_str = human_bytes(int(entry.get("size", 0) or 0))
    mime = entry.get("mime_type") or ""
    suffix = f"  ({mime})" if mime else ""
    return f"- [file] {name}  {size_str}{suffix}  [{handle}]"
