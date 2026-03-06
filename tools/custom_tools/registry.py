"""Persistence layer for custom tool definitions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from config import load_config

logger = logging.getLogger(__name__)


class CustomToolParameter(BaseModel):
    """A single parameter definition for a custom tool."""

    name: str
    type: str
    description: str
    required: bool = True


class CustomToolDefinition(BaseModel):
    """Full definition of a persisted custom tool."""

    id: str
    name: str
    description: str
    type: str  # "command" | "program"
    language: str = "bash"  # "python" | "bash"
    command_template: str = ""
    script_filename: str | None = None
    parameters: list[CustomToolParameter] = []
    dependencies: list[str] = []
    tags: list[str] = []
    created_at: str
    updated_at: str


def _get_registry_path() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "custom_tools" / "registry.json"


def _get_scripts_dir() -> Path:
    # Scripts must live inside virtual_computer.home_dir, which is the directory
    # volume-mounted into the container at /home/computron.
    cfg = load_config()
    return Path(cfg.virtual_computer.home_dir) / "custom_tools" / "scripts"


def load_registry() -> list[CustomToolDefinition]:
    """Read and parse registry.json. Returns empty list if missing."""
    path = _get_registry_path()
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return [CustomToolDefinition.model_validate(entry) for entry in data]
    except Exception:
        logger.exception("Failed to load custom tool registry from %s", path)
        return []


def save_registry(tools: list[CustomToolDefinition]) -> None:
    """Atomically write registry.json."""
    path = _get_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    serialized = [t.model_dump() for t in tools]
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(path)


def add_tool(definition: CustomToolDefinition, *, overwrite: bool = False) -> CustomToolDefinition:
    """Validate name uniqueness, assign id + timestamps, append (or replace), and save."""
    tools = load_registry()
    now = datetime.now(UTC).isoformat()
    existing_idx = next((i for i, t in enumerate(tools) if t.name == definition.name), None)
    if existing_idx is not None:
        if not overwrite:
            msg = f"A custom tool named '{definition.name}' already exists. Pass overwrite=true to replace it."
            raise ValueError(msg)
        # Preserve original id and created_at; bump updated_at.
        existing = tools[existing_idx]
        definition = definition.model_copy(
            update={"id": existing.id, "created_at": existing.created_at, "updated_at": now}
        )
        tools[existing_idx] = definition
    else:
        definition = definition.model_copy(update={"id": str(uuid.uuid4()), "created_at": now, "updated_at": now})
        tools.append(definition)
    save_registry(tools)
    return definition


def get_tool(name: str) -> CustomToolDefinition | None:
    """Look up a tool by exact name."""
    return next((t for t in load_registry() if t.name == name), None)


def search_tools(query: str) -> list[CustomToolDefinition]:
    """Case-insensitive search across name, description, and tags.

    The query is split on whitespace and commas into individual keywords.
    A tool matches if ANY keyword is found in its name, description, or tags.
    """
    import re

    keywords = [k for k in re.split(r"[,\s]+", query.lower()) if k]
    if not keywords:
        return []
    results = []
    for tool in load_registry():
        haystack = " ".join([tool.name, tool.description, *tool.tags]).lower()
        if any(k in haystack for k in keywords):
            results.append(tool)
    return results


def list_tools() -> list[CustomToolDefinition]:
    """Return all tool definitions."""
    return load_registry()


def delete_tool(name: str) -> bool:
    """Delete a tool by name. Also removes any associated script file. Returns True if found."""
    tools = load_registry()
    idx = next((i for i, t in enumerate(tools) if t.name == name), None)
    if idx is None:
        return False
    tool = tools[idx]
    # Remove script file if present
    if tool.script_filename:
        script_path = _get_scripts_dir() / tool.script_filename
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove script file %s", script_path)
    tools.pop(idx)
    save_registry(tools)
    return True


def save_script(tool_id: str, content: str, language: str) -> str:
    """Write script content to the scripts directory. Returns the filename."""
    scripts_dir = _get_scripts_dir()
    scripts_dir.mkdir(parents=True, exist_ok=True)
    ext = "py" if language == "python" else "sh"
    filename = f"{tool_id}.{ext}"
    (scripts_dir / filename).write_text(content, encoding="utf-8")
    return filename


__all__ = [
    "CustomToolDefinition",
    "CustomToolParameter",
    "add_tool",
    "delete_tool",
    "get_tool",
    "list_tools",
    "load_registry",
    "save_registry",
    "save_script",
    "search_tools",
]
