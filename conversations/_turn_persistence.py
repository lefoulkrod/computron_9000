"""TurnPersistence adapter backed by the on-disk conversation store."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ._store import (
    load_loaded_skills,
    save_agent_events,
    save_conversation_title,
    save_loaded_skills,
)
from ._title_generation import generate_conversation_title

if TYPE_CHECKING:
    from sdk.events import AgentEvent

logger = logging.getLogger(__name__)

__all__ = ["DiskTurnPersistence"]


class DiskTurnPersistence:
    """Implements the ``sdk.turn.TurnPersistence`` protocol against the on-disk store."""

    def load_skills(self, conversation_id: str) -> Iterable[str]:
        return load_loaded_skills(conversation_id)

    def save_skills(self, conversation_id: str, skills: Iterable[str]) -> None:
        save_loaded_skills(conversation_id, frozenset(skills))

    def save_events(
        self,
        conversation_id: str,
        events: list[AgentEvent],
    ) -> None:
        save_agent_events(conversation_id, events)

    async def on_new_conversation(
        self,
        conversation_id: str,
        first_message: str,
    ) -> None:
        try:
            title = await generate_conversation_title(first_message)
            save_conversation_title(conversation_id, title)
            logger.info(
                "Generated title for conversation %s: %r",
                conversation_id,
                title,
            )
        except Exception:
            logger.exception(
                "Failed to generate title for conversation %s",
                conversation_id,
            )
