"""Ephemeral key-value scratchpad for agent sessions.

Agents use these tools to take notes during multi-step tasks (e.g. remembering
which card was at which position in a match game). The scratchpad is backed by
a ContextVar so each async request gets its own dict, and is lazily initialized
on first write.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_scratchpad: ContextVar[dict[str, str]] = ContextVar("scratchpad")


def _get_or_init() -> dict[str, str]:
    try:
        return _scratchpad.get()
    except LookupError:
        pad: dict[str, str] = {}
        _scratchpad.set(pad)
        return pad


async def save_to_scratchpad(key: str, value: str) -> dict[str, object]:
    """Store a key-value pair in the ephemeral scratchpad for this agent session.

    Use this to remember intermediate results during multi-step tasks. The
    scratchpad is private to the current request and is discarded when the
    request ends.

    Args:
        key: Short identifier for the note (e.g. "card_3_position", "step_result").
        value: The value to remember.

    Returns:
        Confirmation dict with status and stored key/value.
    """
    pad = _get_or_init()
    pad[key] = value
    logger.debug("Scratchpad save: %s = %r", key, value)
    return {"status": "ok", "key": key, "value": value}


async def recall_from_scratchpad(key: str | None = None) -> dict[str, object]:
    """Recall a value from the ephemeral scratchpad, or all stored items.

    Args:
        key: The key to look up. Pass None (or omit) to retrieve all stored
            key-value pairs.

    Returns:
        Dict with the requested value, all items, or a not_found status.
    """
    pad = _get_or_init()
    if key is None:
        return {"status": "ok", "items": dict(pad)}
    if key in pad:
        return {"status": "ok", "key": key, "value": pad[key]}
    return {"status": "not_found", "key": key}
