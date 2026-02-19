"""Context-bound event publishing utilities for the events layer.

This module exposes an asyncio-friendly API to publish AssistantResponse events
without passing dispatcher handles through every call. It relies on a
contextvars.ContextVar to track the currently active dispatcher for the
duration of a single user message handling coroutine.

Guidelines:
- No blocking calls; publishing delegates to the active dispatcher, which is
  responsible for scheduling subscriber callbacks appropriately.
- Safe no-op behavior when no dispatcher is set (useful in tests or
  components that are not running under the message handling flow).
"""

from __future__ import annotations

import itertools
import logging
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Avoid runtime import cycles; only needed for typing
    from collections.abc import AsyncIterator, Generator

from .dispatcher import EventDispatcher, Handler
from .models import AssistantResponse

logger = logging.getLogger(__name__)


# Active dispatcher for the current coroutine context.
_current_dispatcher: ContextVar[EventDispatcher | None] = ContextVar(
    "assistant_events_current_dispatcher", default=None
)

# Stack of (context_id, agent_name) frames for nested agent/tool executions.
_context_stack: ContextVar[tuple[tuple[str, str | None], ...]] = ContextVar(
    "assistant_events_context_stack", default=()
)

_subcontext_counter = itertools.count(1)
_ROOT_CONTEXT_ID = "root"


def _make_child_context_id(label: str | None = None) -> str:
    """Create a child context id derived from the current stack top."""
    stack = _context_stack.get()
    parent_id = stack[-1][0] if stack else _ROOT_CONTEXT_ID
    raw = (label or "child").lower()
    safe = "".join(c if c.isalnum() else "_" for c in raw).strip("_") or "child"
    return f"{parent_id}.{safe}.{next(_subcontext_counter)}"


@contextmanager
def agent_span(
    agent_name: str | None = None,
    context_id: str | None = None,
) -> Generator[str, None, None]:
    """Push an attribution frame for the duration of the block.

    Events published inside will be tagged with the given agent name and an
    incremented depth. If context_id is omitted, one is generated from the
    current stack.

    Args:
        agent_name: Human-readable agent name for event attribution.
        context_id: Optional explicit context id. If omitted, one is generated.

    Yields:
        str: The resolved context id pushed onto the stack.

    Example:
        with agent_span("Browser Agent"):
            publish_event(AssistantResponse(thinking="Navigating..."))
    """
    if context_id is None:
        context_id = _make_child_context_id(agent_name)
    token = _context_stack.set((*_context_stack.get(), (context_id, agent_name)))
    try:
        yield context_id
    finally:
        _context_stack.reset(token)


def publish_event(event: AssistantResponse) -> None:
    """Publish an AssistantResponse via the dispatcher bound to this context.

    No-op when no dispatcher is set. The event is enriched with the current
    agent name and depth from the context stack before dispatch.

    Args:
        event: The AssistantResponse instance to publish.
    """
    dispatcher = _current_dispatcher.get()
    if dispatcher is None:
        # Intentionally a low-level debug message to avoid noisy logs in contexts
        # where publishing is optional.
        logger.debug("No active dispatcher; dropping event publish request.")
        return

    stack = _context_stack.get()
    try:
        dispatcher.publish(event.model_copy(update={
            "agent_name": stack[-1][1] if stack else None,
            "depth": len(stack) - 1 if stack else 0,
        }))
    except Exception:  # pragma: no cover - defensive logging path
        logger.exception("Failed to publish AssistantResponse event")


@asynccontextmanager
async def event_context(
    handler: Handler | None = None,
) -> AsyncIterator[None]:
    """Create a dispatcher, bind it to context, and optionally subscribe a handler.

    This helper ensures:
    - A fresh EventDispatcher is created per context
    - The dispatcher is bound to the context var so ``publish_event`` works
    - If a handler is provided, it is subscribed for the duration of the context
    - In-flight async handler tasks are drained before teardown
    - Teardown always occurs, even if the body raises

    Use ``agent_span`` inside this context to attribute events to specific agents.

    Args:
        handler: Optional subscriber callable (sync or async).

    Yields:
        None
    """
    dispatcher = EventDispatcher()
    token = _current_dispatcher.set(dispatcher)
    try:
        if handler is not None:
            async with dispatcher.subscription(handler):
                yield None
        else:
            yield None
    finally:
        await dispatcher.drain()
        _current_dispatcher.reset(token)
