"""Per-conversation state owned by callers (channels, handlers, tools).

Kept in its own module so importers that only need the dataclass don't
pay the cost of pulling in ``TurnExecutor`` + its transitive deps —
that matters for modules below the SDK in the dependency graph (e.g.
the ``conversations`` package's cache) where importing the executor
would form a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdk.context._history import ConversationHistory

__all__ = ["Conversation"]


@dataclass
class Conversation:
    """Per-conversation state owned by the caller.

    Attributes:
        id: Unique conversation identifier.
        history: The conversation history.
    """

    id: str
    history: ConversationHistory
