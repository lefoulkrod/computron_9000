"""React loop: iterative LLM-call → tool-execution cycle and turn lifecycle.

This package provides:
- ``run_turn``: Async function driving the chat/tool loop.
- ``turn_scope``: Async context manager for conversation turn lifecycle.
- ``TurnExecutor``: High-level executor that encapsulates agent resolution,
  memory injection, skill restoration, hook wiring, and persistence.
- ``Conversation``: Per-conversation state owned by a channel.
- Stop/nudge signaling utilities for user-initiated control.
"""

from ._execution import ToolLoopError, run_turn
from ._turn import (
    StopRequestedError,
    any_turn_active,
    check_stop,
    drain_nudges,
    get_conversation_id,
    is_turn_active,
    queue_nudge,
    request_stop,
    turn_scope,
)

__all__ = [
    "Conversation",
    "StopRequestedError",
    "ToolLoopError",
    "TurnExecutor",
    "any_turn_active",
    "check_stop",
    "drain_nudges",
    "get_conversation_id",
    "is_turn_active",
    "queue_nudge",
    "request_stop",
    "run_turn",
    "turn_scope",
]


def __getattr__(name: str) -> object:
    """Lazy imports to avoid circular dependency with sdk top-level."""
    if name in ("Conversation", "TurnExecutor"):
        from ._executor import Conversation, TurnExecutor

        return {"Conversation": Conversation, "TurnExecutor": TurnExecutor}[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)