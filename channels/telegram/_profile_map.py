"""Per-chat agent-profile selection.

A simple ``chat_id -> profile_id`` mapping the channel consults on every
turn. Empty mapping means the channel falls back to its configured default.
Persistence is in-memory only today; a chat that hits a fresh process
restarts at the default until the user picks again.
"""

from __future__ import annotations

from typing import MutableMapping

__all__ = ["ProfileMap"]


class ProfileMap:
    """Maps Telegram chat IDs to the agent profile ID active for that chat."""

    def __init__(self) -> None:
        self._map: MutableMapping[int, str] = {}

    def get(self, chat_id: int) -> str | None:
        """Return the chosen profile ID for ``chat_id`` or ``None``."""
        return self._map.get(chat_id)

    def set(self, chat_id: int, profile_id: str) -> None:
        """Record the user's profile choice for this chat."""
        self._map[chat_id] = profile_id

    def clear(self, chat_id: int) -> None:
        """Drop the recorded choice so this chat reverts to the default."""
        self._map.pop(chat_id, None)
