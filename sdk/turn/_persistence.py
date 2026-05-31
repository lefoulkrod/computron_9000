"""Protocol for persistence hooks fired by channels around a turn.

This is the small interface the channel uses to: hydrate per-conversation
skill state on cache miss, flush it after each turn, persist the agent
event stream, and fire a first-turn hook (typically title generation).

Channels that don't want persistence simply pass ``None`` instead of an
implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sdk.events._models import AgentEvent

__all__ = ["TurnPersistence"]


class TurnPersistence(Protocol):
    """Optional persistence surface used by channels around a turn."""

    def load_skills(self, conversation_id: str) -> Iterable[str]:
        """Return persisted skill names to restore for this conversation."""

    def save_skills(self, conversation_id: str, skills: Iterable[str]) -> None:
        """Persist the set of currently-loaded skill names."""

    def save_events(
        self,
        conversation_id: str,
        events: list[AgentEvent],
    ) -> None:
        """Persist agent lifecycle events captured during the turn."""

    async def on_new_conversation(
        self,
        conversation_id: str,
        first_message: str,
    ) -> None:
        """Hook fired once when a conversation runs its first turn.

        Typical use: generate and persist a conversation title.
        """
