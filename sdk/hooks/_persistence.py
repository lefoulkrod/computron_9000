"""Hook that persists conversation history at turn end."""

from __future__ import annotations

import logging
from typing import Any

from sdk.context import ConversationHistory

logger = logging.getLogger(__name__)


class PersistenceHook:
    """Saves conversation history when the turn ends."""

    def __init__(
        self,
        *,
        conversation_id: str,
        history: ConversationHistory,
    ) -> None:
        self._conversation_id = conversation_id
        self._history = history

    def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        """Persist conversation history."""
        from conversations import save_conversation_history

        try:
            save_conversation_history(
                self._conversation_id, self._history.non_system_messages,
            )
        except Exception:
            logger.exception("Failed to save conversation history for '%s'", self._conversation_id)
