"""Persistent key-value memory for COMPUTRON, stored in the app home directory."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import load_config

logger = logging.getLogger(__name__)

# Storage format: {"key": {"value": "...", "hidden": false}}


@dataclass
class MemoryEntry:
    """A single stored memory with its visibility state."""

    value: str
    hidden: bool = False


def _memory_path() -> Path:
    return Path(load_config().settings.home_dir) / "memory.json"


def _load_raw() -> dict[str, MemoryEntry]:
    path = _memory_path()
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return {
            k: MemoryEntry(value=str(v["value"]), hidden=bool(v.get("hidden", False)))
            for k, v in data.items()
        }
    except Exception:
        logger.exception("Failed to load memory from %s", path)
        return {}


def _save_raw(data: dict[str, MemoryEntry]) -> None:
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {k: {"value": e.value, "hidden": e.hidden} for k, e in data.items()}
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    tmp.replace(path)


def load_memory() -> dict[str, MemoryEntry]:
    """Load all stored memories."""
    return _load_raw()


def set_key_hidden(key: str, hidden: bool) -> None:
    """Mark a memory key as hidden or visible in the UI."""
    data = _load_raw()
    if key in data:
        data[key].hidden = hidden
        _save_raw(data)


async def remember(key: str, value: str) -> dict[str, object]:
    """Store a persistent memory that will be available in all future sessions.

    Use this to remember facts about the user, their preferences, useful context,
    or anything worth recalling later. Memories persist indefinitely.

    Args:
        key: Short identifier for the memory (e.g. "user_timezone", "preferred_language").
        value: The value to remember.

    Returns:
        Confirmation dict with status and stored key/value.
    """
    data = _load_raw()
    # preserve existing hidden state when updating a key
    existing_hidden = data[key].hidden if key in data else False
    data[key] = MemoryEntry(value=value, hidden=existing_hidden)
    _save_raw(data)
    logger.info("Memory stored: %s = %r", key, value)
    return {"status": "ok", "key": key, "value": value}


async def forget(key: str) -> dict[str, object]:
    """Remove a stored memory by key.

    Args:
        key: The memory key to delete.

    Returns:
        Confirmation dict with status.
    """
    data = _load_raw()
    if key not in data:
        return {"status": "not_found", "key": key}
    del data[key]
    _save_raw(data)
    logger.info("Memory forgotten: %s", key)
    return {"status": "ok", "key": key}
