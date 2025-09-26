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
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Avoid runtime import cycles; only needed for typing
    from collections.abc import AsyncIterator

from .dispatcher import EventDispatcher, Handler
from .models import AssistantResponse, DispatchEvent

logger = logging.getLogger(__name__)


# Holds the currently active dispatcher for the running coroutine context.
_current_dispatcher: ContextVar[EventDispatcher | None] = ContextVar(
    "assistant_events_current_dispatcher", default=None
)

# Tracks whether content should be suppressed (e.g., while executing tools).

# Stack of context identifiers for nested agent/tool executions.
_context_stack: ContextVar[tuple[str, ...]] = ContextVar(
    "assistant_events_context_stack", default=()
)

# Monotonic counter for generating child context identifiers.
_subcontext_counter = itertools.count(1)

DEFAULT_ROOT_CONTEXT_ID = "root"


def get_current_dispatcher() -> EventDispatcher | None:
    """Return the dispatcher bound to the current context, if any.

    Returns:
        Optional[_DispatcherLike]: The active dispatcher or None if none is set.
    """
    return _current_dispatcher.get()


def set_current_dispatcher(dispatcher: EventDispatcher | None) -> Token:
    """Set the current dispatcher for this context.

    Args:
        dispatcher: Dispatcher-like instance to bind, or None to clear.

    Returns:
        Token: A context token that can be used to reset the previous value.
    """
    return _current_dispatcher.set(dispatcher)


def reset_current_dispatcher(token: Token) -> None:
    """Reset the current dispatcher to the value prior to the associated set.

    Args:
        token: Token returned by set_current_dispatcher.
    """
    _current_dispatcher.reset(token)


def push_context_id(context_id: str | None = None) -> tuple[Token, str]:
    """Push a new context identifier onto the stack and return the resolved id."""
    stack = list(_context_stack.get())
    if context_id is None:
        base = stack[-1] if stack else DEFAULT_ROOT_CONTEXT_ID
        context_id = f"{base}:{next(_subcontext_counter)}"
    stack.append(context_id)
    token = _context_stack.set(tuple(stack))
    return token, context_id


def reset_context_id(token: Token) -> None:
    """Restore the context stack to the state captured by ``token``."""
    _context_stack.reset(token)


def current_context_id() -> str:
    """Return the current context identifier (or root if none set)."""
    stack = _context_stack.get()
    if not stack:
        return DEFAULT_ROOT_CONTEXT_ID
    return stack[-1]


def current_parent_context_id() -> str | None:
    """Return the parent context id if available."""
    stack = _context_stack.get()
    if len(stack) < 2:
        return None
    return stack[-2]


def current_context_depth() -> int:
    """Return the current context depth (root == 0)."""
    stack = _context_stack.get()
    if not stack:
        return 0
    return len(stack) - 1


def make_child_context_id(label: str | None = None) -> str:
    """Create a deterministic child context id using the current context as base."""
    parent = current_context_id()
    raw_label = (label or "child").lower()
    safe_label = "".join(ch if ch.isalnum() else "_" for ch in raw_label).strip("_") or "child"
    suffix = next(_subcontext_counter)
    return f"{parent}.{safe_label}.{suffix}"


@contextmanager
def use_context_id(context_id: str | None = None):
    """Push a context id for the duration of the context manager."""
    token, resolved = push_context_id(context_id)
    try:
        yield resolved
    finally:
        reset_context_id(token)


def publish_event(event: AssistantResponse) -> None:
    """Publish an AssistantResponse via the dispatcher bound to this context.

    This function is safe to call even if no dispatcher is set; in that case
    it becomes a no-op. This makes it convenient to call from anywhere inside
    the message handling code without having to plumb the dispatcher explicitly.

    Args:
        event: The AssistantResponse instance describing content/thinking/data/event.
    """
    dispatcher = get_current_dispatcher()
    if dispatcher is None:
        # Intentionally a low-level debug message to avoid noisy logs in contexts
        # where publishing is optional.
        logger.debug("No active dispatcher; dropping event publish request.")
        return

    try:
        dispatch_event = DispatchEvent(
            context_id=current_context_id(),
            parent_context_id=current_parent_context_id(),
            depth=current_context_depth(),
            payload=event,
        )
        dispatcher.publish(dispatch_event)
    except Exception:  # pragma: no cover - defensive logging path
        # We swallow exceptions here to avoid tearing down the message handling
        # flow due to subscriber issues. The dispatcher implementation should
        # also be robust, but we log with context just in case.
        logger.exception("Failed to publish AssistantResponse event")


@asynccontextmanager
async def event_context(
    handler: Handler | None = None,
    *,
    context_id: str | None = None,
) -> AsyncIterator[EventDispatcher]:
    """Create a dispatcher, bind it to context, and optionally subscribe a handler.

    This helper ensures:
    - A fresh EventDispatcher is created per context
    - The dispatcher is bound to the context var so ``publish_event`` works
    - If a handler is provided, it is subscribed for the duration of the context
    - Teardown always occurs (unsubscribe + context reset), even if the body raises

    Args:
        handler: Optional subscriber callable (sync or async).

    Yields:
        EventDispatcher: The dispatcher instance bound to the current context.
    """
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher_token = set_current_dispatcher(dispatcher)
    context_token, _ = push_context_id(context_id)

    if handler is None:
        try:
            yield dispatcher
        finally:
            try:
                reset_context_id(context_token)
                reset_current_dispatcher(dispatcher_token)
            except Exception:  # pragma: no cover - defensive cleanup
                logger.exception("Failed to reset dispatcher context in event_context")
        return

    try:
        async with dispatcher.subscription(handler):
            yield dispatcher
    finally:
        try:
            reset_context_id(context_token)
            reset_current_dispatcher(dispatcher_token)
        except Exception:  # pragma: no cover - defensive cleanup
            logger.exception("Failed to reset dispatcher context in event_context")
