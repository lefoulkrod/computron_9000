"""Per-conversation state owned by callers (channels, handlers, tools).

Kept in its own module so importers that only need the dataclass don't
pay the cost of pulling in ``TurnExecutor`` + its transitive deps —
that matters for modules below the SDK in the dependency graph (e.g.
the ``conversations`` package's cache) where importing the executor
would form a cycle.

``AgentState`` is referenced via ``TYPE_CHECKING`` for the same reason:
``sdk.skills._registry`` eagerly pulls in every registered skill's tool
modules, which a bare cache miss has no business loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sdk.context._history import ConversationHistory

if TYPE_CHECKING:
    from sdk.skills import AgentState

__all__ = ["Conversation"]


@dataclass
class Conversation:
    """Per-conversation state owned by the caller.

    Attributes:
        id: Unique conversation identifier.
        history: The conversation history.
        agent_state: Loaded skills + base tools that survive across turns.
            Set by the caller (channels hydrate on cache miss; one-shot
            callers like spawn_agent construct fresh). ``None`` means
            "not yet populated"; callers should fill it before the first
            turn runs.
    """

    id: str
    history: ConversationHistory
    agent_state: AgentState | None = None
