"""Hook that persists conversation history at turn end."""

from __future__ import annotations

import logging

from sdk.context import ConversationHistory

logger = logging.getLogger(__name__)


class PersistenceHook:
    """Saves conversation history when the turn ends.

    For sub-agents, pass ``sub_agent_name`` and ``sub_agent_id`` to write
    to the conversation's ``sub_agents/`` directory instead of overwriting
    the main history.
    """

    def __init__(
        self,
        *,
        conversation_id: str,
        history: ConversationHistory,
        sub_agent_name: str | None = None,
        sub_agent_id: str | None = None,
    ) -> None:
        self._conversation_id = conversation_id
        self._history = history
        self._sub_agent_name = sub_agent_name
        self._sub_agent_id = sub_agent_id

    def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        """Persist conversation history."""
        try:
            if self._sub_agent_name and self._sub_agent_id:
                from conversations import save_sub_agent_history

                save_sub_agent_history(
                    self._conversation_id,
                    self._sub_agent_name,
                    self._sub_agent_id,
                    self._history.non_system_messages,
                )
            else:
                from conversations import save_conversation_history

                save_conversation_history(
                    self._conversation_id, self._history.non_system_messages,
                )
        except Exception:
            logger.exception("Failed to save conversation history for '%s'", self._conversation_id)
