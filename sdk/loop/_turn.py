"""Turn lifecycle management for the agent SDK.

A *turn* is a single user message → assistant response cycle, including all
sub-agent work and tool calls that happen in between. This module provides the
async context manager that sets up and tears down everything a turn needs:

- An event dispatcher bound to a ContextVar so ``publish_event`` works
- A per-session stop event so ``check_stop`` / ``request_stop`` work
- Session liveness tracking (``is_turn_active``)
- Per-session nudge queues (``queue_nudge`` / ``drain_nudges``)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from sdk.events._context import _current_dispatcher
from sdk.events._dispatcher import EventDispatcher, Handler

logger = logging.getLogger(__name__)


class StopRequestedError(Exception):
    """Raised at safe checkpoints when the user requests a stop."""


_DEFAULT_SESSION_ID = "default"

# Sessions that currently have an active turn.
_active_sessions: set[str] = set()

# Per-session stop events so the HTTP stop endpoint can target a specific
# session without interfering with others.
_active_stop_events: dict[str, asyncio.Event] = {}

# Stop event bound to the currently active turn, accessible without passing
# it through every call frame.
_stop_event: ContextVar[asyncio.Event | None] = ContextVar(
    "turn_stop_event", default=None
)

# Session ID for the current coroutine context, set inside turn_scope()
# and inherited by sub-agents automatically via ContextVar semantics.
_session_id: ContextVar[str | None] = ContextVar("turn_session_id", default=None)

# Per-session nudge queues keyed by session_id.
_nudge_queues: dict[str, list[str]] = {}


def request_stop(session_id: str | None = None) -> None:
    """Signal the active turn to stop at the next safe checkpoint.

    Args:
        session_id: Target a specific session. If None, stops the default session.
    """
    sid = session_id or _DEFAULT_SESSION_ID
    event = _active_stop_events.get(sid)
    if event is not None:
        event.set()


def check_stop() -> None:
    """Raise StopRequestedError if a stop has been requested for this turn.

    Call this at safe checkpoints (e.g. top of tool loop, before each tool
    execution) to allow clean interruption without cancelling tasks mid-await.
    """
    event = _stop_event.get()
    if event is not None and event.is_set():
        raise StopRequestedError()


def is_turn_active(session_id: str | None = None) -> bool:
    """Return True if the given session has an active turn."""
    sid = session_id or _DEFAULT_SESSION_ID
    return sid in _active_sessions


def queue_nudge(session_id: str, message: str) -> None:
    """Append a nudge message to the session's queue."""
    q = _nudge_queues.get(session_id)
    if q is not None:
        q.append(message)


def drain_nudges() -> list[str]:
    """Pop and return all queued nudge messages for the current session."""
    sid = _session_id.get()
    if sid is None:
        return []
    q = _nudge_queues.get(sid)
    if not q:
        return []
    messages = list(q)
    q.clear()
    return messages


@asynccontextmanager
async def turn_scope(
    handler: Handler | None = None,
    session_id: str | None = None,
) -> AsyncIterator[None]:
    """Set up and tear down everything needed for a single conversation turn.

    This ensures:
    - A fresh EventDispatcher is created and bound so ``publish_event`` works
    - A fresh stop event is created and bound so ``check_stop`` works from any
      depth without parameter passing
    - The session is registered as active so ``is_turn_active`` returns True
    - A nudge queue is created for the session
    - If a handler is provided, it is subscribed for the duration of the turn
    - In-flight async handler tasks are drained before teardown
    - Teardown always occurs, even if the body raises

    Args:
        handler: Optional subscriber callable (sync or async).
        session_id: Session identifier for per-session isolation.

    Yields:
        None
    """
    sid = session_id or _DEFAULT_SESSION_ID
    dispatcher = EventDispatcher()
    stop_event = asyncio.Event()
    _active_sessions.add(sid)
    _active_stop_events[sid] = stop_event
    _nudge_queues[sid] = []
    dispatcher_token = _current_dispatcher.set(dispatcher)
    stop_token = _stop_event.set(stop_event)
    session_token = _session_id.set(sid)
    try:
        if handler is not None:
            async with dispatcher.subscription(handler):
                yield None
        else:
            yield None
    finally:
        await dispatcher.drain()
        _current_dispatcher.reset(dispatcher_token)
        _stop_event.reset(stop_token)
        _session_id.reset(session_token)
        _active_sessions.discard(sid)
        _active_stop_events.pop(sid, None)
        _nudge_queues.pop(sid, None)
