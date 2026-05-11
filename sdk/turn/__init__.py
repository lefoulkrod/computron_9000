"""React loop: iterative LLM-call → tool-execution cycle and turn lifecycle.

This package provides:
- ``run_turn``: Async function driving the chat/tool loop.
- ``turn_scope``: Async context manager for conversation turn lifecycle.
- Stop/nudge signaling utilities for user-initiated control.
"""

from ._execution import ToolLoopError, run_turn
from ._nudge_queue import drain_nudges, queue_nudge, register_nudge_queue, unregister_nudge_queue
from ._turn import (
    StopRequestedError,
    any_turn_active,
    check_stop,
    get_conversation_id,
    is_turn_active,
    request_stop,
    turn_scope,
)

__all__ = [
    "StopRequestedError",
    "ToolLoopError",
    "any_turn_active",
    "check_stop",
    "drain_nudges",
    "get_conversation_id",
    "is_turn_active",
    "queue_nudge",
    "register_nudge_queue",
    "request_stop",
    "run_turn",
    "turn_scope",
    "unregister_nudge_queue",
]
