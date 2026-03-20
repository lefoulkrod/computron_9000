"""React loop: iterative LLM-call → tool-execution cycle and turn lifecycle.

This package provides:
- ``run_tool_call_loop``: Main async generator driving the chat/tool loop.
- ``turn_scope``: Async context manager for conversation turn lifecycle.
- Stop/nudge signaling utilities for user-initiated control.
"""

from ._tool_loop import ToolLoopError, run_tool_call_loop
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
    "StopRequestedError",
    "ToolLoopError",
    "any_turn_active",
    "check_stop",
    "drain_nudges",
    "get_conversation_id",
    "is_turn_active",
    "queue_nudge",
    "request_stop",
    "run_tool_call_loop",
    "turn_scope",
]
