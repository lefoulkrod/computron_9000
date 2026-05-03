"""Shared formatting helpers for Drive agent tools."""

from __future__ import annotations

from typing import Any

_MIME_SHORTCUTS = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Form",
    "application/vnd.google-apps.drawing": "Google Drawing",
    "application/vnd.google-apps.shortcut": "Shortcut",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "application/pdf": "PDF",
}


def format_file(f: dict[str, Any]) -> str:
    fid = f.get("id", "?")
    name = f.get("name", "(unnamed)")
    mime = f.get("mimeType", "")
    size = f.get("size")
    kind = "folder" if mime == "application/vnd.google-apps.folder" else short_mime(mime)
    size_str = f" ({format_size(int(size))})" if size else ""
    return f"- [{fid}] {name}  —  {kind}{size_str}"


def short_mime(mime: str) -> str:
    return _MIME_SHORTCUTS.get(mime, mime.split("/")[-1] if "/" in mime else mime)


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"
