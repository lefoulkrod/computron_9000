"""Pluggable context management strategies."""

import logging
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ._history import ConversationHistory
from ._models import ContextStats

logger = logging.getLogger(__name__)


class TriggerPoint(StrEnum):
    """When a strategy should be evaluated."""

    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_CALL = "after_model_call"


@runtime_checkable
class ContextStrategy(Protocol):
    """Interface for context management strategies."""

    @property
    def trigger(self) -> TriggerPoint:
        """When this strategy should be evaluated."""
        ...

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        """Whether this strategy needs to act given the current state."""
        ...

    def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Mutate *history* to reduce context usage."""
        ...


class DropOldMessagesStrategy:
    """Drops the oldest non-system messages when context fill exceeds a threshold.

    Args:
        threshold: Fill ratio above which the strategy activates (0.0–1.0).
        keep_recent: Minimum number of recent non-system messages to preserve.
    """

    def __init__(self, threshold: float = 0.85, keep_recent: int = 4) -> None:
        self._threshold = threshold
        self._keep_recent = keep_recent

    @property
    def trigger(self) -> TriggerPoint:
        return TriggerPoint.BEFORE_MODEL_CALL

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        return stats.fill_ratio >= self._threshold

    def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Drop oldest non-system messages, keeping *keep_recent* recent ones."""
        non_system = history.non_system_messages
        if len(non_system) <= self._keep_recent:
            return

        # Number of messages to drop (leave keep_recent)
        to_drop = len(non_system) - self._keep_recent

        # Determine the start index in the underlying list.
        # If there's a system message at index 0, non-system starts at 1.
        start = 1 if history.system_message is not None else 0
        end = start + to_drop

        logger.info(
            "DropOldMessages: fill_ratio=%.2f dropping %d messages [%d:%d)",
            stats.fill_ratio,
            to_drop,
            start,
            end,
        )
        history.drop_range(start, end)
