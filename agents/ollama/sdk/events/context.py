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

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Avoid runtime import cycles; only needed for typing
    from collections.abc import AsyncIterator

    from .models import AssistantResponse

from .dispatcher import EventDispatcher, Handler

logger = logging.getLogger(__name__)


# Holds the currently active dispatcher for the running coroutine context.
_current_dispatcher: ContextVar[EventDispatcher | None] = ContextVar(
    "assistant_events_current_dispatcher", default=None
)

# Tracks whether content should be suppressed (e.g., while executing tools).
_suppress_content: ContextVar[bool] = ContextVar("assistant_events_suppress_content", default=False)


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


def publish_event(event: AssistantResponse) -> None:
    """Publish an AssistantResponse via the dispatcher bound to this context.

    This function is safe to call even if no dispatcher is set; in that case
    it becomes a no-op. This makes it convenient to call from anywhere inside
    the message handling code without having to plumb the dispatcher explicitly.

    Args:
        event: The AssistantResponse instance describing content/thinking/data/event.
    """
    if suppress_content_enabled() and event.content is not None:
        event = event.model_copy(update={"content": None})

    dispatcher = get_current_dispatcher()
    if dispatcher is None:
        # Intentionally a low-level debug message to avoid noisy logs in contexts
        # where publishing is optional.
        logger.debug("No active dispatcher; dropping event publish request.")
        return

    try:
        dispatcher.publish(event)
    except Exception:  # pragma: no cover - defensive logging path
        # We swallow exceptions here to avoid tearing down the message handling
        # flow due to subscriber issues. The dispatcher implementation should
        # also be robust, but we log with context just in case.
        logger.exception("Failed to publish AssistantResponse event")


@asynccontextmanager
async def event_context(
    handler: Handler | None = None,
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
    token = set_current_dispatcher(dispatcher)

    if handler is None:
        try:
            yield dispatcher
        finally:
            try:
                reset_current_dispatcher(token)
            except Exception:  # pragma: no cover - defensive cleanup
                logger.exception("Failed to reset dispatcher context in event_context")
        return

    try:
        async with dispatcher.subscription(handler):
            yield dispatcher
    finally:
        try:
            reset_current_dispatcher(token)
        except Exception:  # pragma: no cover - defensive cleanup
            logger.exception("Failed to reset dispatcher context in event_context")


def suppress_content_enabled() -> bool:
    """Return True when content emission is currently suppressed."""
    return _suppress_content.get()


def enable_content_suppression() -> Token:
    """Enable content suppression for the current context."""
    return _suppress_content.set(True)


def reset_content_suppression(token: Token) -> None:
    """Restore content suppression state using the provided token."""
    _suppress_content.reset(token)
