"""Disk-backed key-value scratchpad for agent sessions.

Agents use these tools to take notes during multi-step tasks (e.g. remembering
which card was at which position in a match game, or saving key findings from
tool results before they get cleared from context).

Backed by a JSON file per conversation at
``~/.computron_9000/conversations/{conv_id}/scratchpad.json``, with an
in-memory cache for fast reads. Each write flushes to disk so the scratchpad
can be inspected externally.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path

from config import load_config
from sdk.turn import get_conversation_id

logger = logging.getLogger(__name__)

# In-memory cache keyed by conversation ID for fast reads within a session.
_cache: ContextVar[dict[str, str]] = ContextVar("scratchpad_cache")


def _scratchpad_path(conversation_id: str) -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "conversations" / conversation_id / "scratchpad.json"


def _load_from_disk(conversation_id: str) -> dict[str, str]:
    """Load scratchpad from disk, returning empty dict if not found."""
    path = _scratchpad_path(conversation_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Failed to load scratchpad from %s", path)
        return {}


def _flush_to_disk(conversation_id: str, pad: dict[str, str]) -> None:
    """Write scratchpad to disk atomically."""
    path = _scratchpad_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pad, indent=2), encoding="utf-8")
    tmp.replace(path)


def _get_or_init() -> tuple[dict[str, str], str]:
    """Return (pad, conversation_id), loading from disk on first access."""
    conv_id = get_conversation_id() or "default"
    try:
        pad = _cache.get()
    except LookupError:
        pad = _load_from_disk(conv_id)
        _cache.set(pad)
    return pad, conv_id


async def save_to_scratchpad(key: str, value: str) -> dict[str, object]:
    """Store a key-value pair in the scratchpad for this conversation.

    Use this to remember intermediate results during multi-step tasks. The
    scratchpad persists to disk and can be inspected externally.

    Args:
        key: Short identifier for the note (e.g. "card_3_position", "step_result").
        value: The value to remember.

    Returns:
        Confirmation dict with status and stored key/value.
    """
    pad, conv_id = _get_or_init()
    pad[key] = value
    _flush_to_disk(conv_id, pad)
    logger.debug("Scratchpad save: %s = %r (conv=%s)", key, value, conv_id)
    return {"status": "ok", "key": key, "value": value}


async def recall_from_scratchpad(key: str | None = None) -> dict[str, object]:
    """Recall a value from the scratchpad, or all stored items.

    Always reads from disk so cross-agent writes are visible immediately.

    Args:
        key: The key to look up. Pass None (or omit) to retrieve all stored
            key-value pairs.

    Returns:
        Dict with the requested value, all items, or a not_found status.
    """
    conv_id = get_conversation_id() or "default"
    pad = _load_from_disk(conv_id)
    # Refresh the in-memory cache so subsequent writes merge correctly.
    _cache.set(pad)
    if key is None:
        return {"status": "ok", "items": dict(pad)}
    if key in pad:
        return {"status": "ok", "key": key, "value": pad[key]}
    return {"status": "not_found", "key": key}
