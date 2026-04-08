"""Lightweight mapping between Telegram chat IDs and agent conversation IDs."""

from __future__ import annotations

import uuid
from typing import MutableMapping

__all__ = ["ConversationMap"]


class ConversationMap:
    """Maps Telegram chat IDs to agent conversation IDs.

    Default convention: ``telegram_{chat_id}``.  When a user issues /new,
    a fresh UUID-based suffix is appended so the agent starts a new context.
    """

    def __init__(self) -> None:
        self._map: MutableMapping[int, str] = {}

    # -- lookup ---------------------------------------------------------

    def get(self, chat_id: int) -> str:
        """Return the conversation ID for *chat_id*, creating a default if absent."""
        return self._map.setdefault(chat_id, f"telegram_{chat_id}")

    # -- reset (used by /new) -------------------------------------------

    def reset(self, chat_id: int) -> str:
        """Assign a brand-new conversation ID for *chat_id*.

        The new ID is ``telegram_{chat_id}_{uuid4_short}`` so it's unique
        but still traceable to the originating chat.
        """
        short = uuid.uuid4().hex[:8]
        conv_id = f"telegram_{chat_id}_{short}"
        self._map[chat_id] = conv_id
        return conv_id

    # -- introspection --------------------------------------------------

    def conversation_id_for(self, chat_id: int) -> str | None:
        """Return the current conversation ID without side-effects, or ``None``."""
        return self._map.get(chat_id)