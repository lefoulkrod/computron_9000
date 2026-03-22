"""Hook that persists conversation and sub-agent histories at turn end."""

from __future__ import annotations

import logging
from typing import Any

from sdk.context import ConversationHistory

logger = logging.getLogger(__name__)


class PersistenceHook:
    """Saves conversation history and sub-agent histories when the turn ends."""

    def __init__(
        self,
        *,
        conversation_id: str,
        history: ConversationHistory,
    ) -> None:
        self._conversation_id = conversation_id
        self._history = history

    def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        """Persist conversation and sub-agent histories."""
        from conversations import save_conversation_history, save_sub_agent_histories
        from sdk.events import get_sub_agent_histories

        try:
            save_conversation_history(
                self._conversation_id, self._history.non_system_messages,
            )
        except Exception:
            logger.exception("Failed to save conversation history for '%s'", self._conversation_id)

        try:
            sub_histories = get_sub_agent_histories()
            if sub_histories:
                save_sub_agent_histories(self._conversation_id, sub_histories)
        except Exception:
            logger.exception("Failed to save sub-agent histories for '%s'", self._conversation_id)
