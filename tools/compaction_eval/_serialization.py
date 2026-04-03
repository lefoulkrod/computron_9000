"""Thin wrapper around the strategy module's serialization."""

from __future__ import annotations

import copy
from typing import Any

from sdk.context._strategy import _serialize_messages


def serialize_messages(messages: list[dict[str, Any]]) -> str:
    """Serialize messages into the same text format the summarizer sees.

    Makes a deep copy so the caller's data is never mutated (the underlying
    function modifies messages in place for dedup).
    """
    return _serialize_messages(copy.deepcopy(messages))
