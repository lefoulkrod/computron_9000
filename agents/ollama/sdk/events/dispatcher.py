"""Asyncio-friendly event dispatcher for assistant events.

The dispatcher maintains a per-instance set of subscribers and provides:
- subscribe/unsubscribe: manage handlers
- publish: schedule all subscribers with the emitted event
- subscription: async context manager to auto-unsubscribe on exit
- reset: clear all subscribers (useful for test isolation)

Subscribers may be sync or async callables. Sync handlers are scheduled with
the current loop's call_soon to avoid blocking. Async handlers are executed via
asyncio.create_task. Errors in handlers are logged and do not propagate to the
publisher.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager, suppress
from inspect import iscoroutinefunction
from typing import Any

from .models import AssistantResponse

logger = logging.getLogger(__name__)


Handler = Callable[[AssistantResponse], Any]


class EventDispatcher:
    """Manage and fan out AssistantResponse events to subscribers.

    Thread-compatible within a single asyncio loop, but designed for use in
    an asyncio context; does not block the loop.
    """

    __slots__ = ("_subscribers", "_tasks")

    def __init__(self) -> None:
        """Initialize a dispatcher with no subscribers and empty task set."""
        self._subscribers: list[Handler] = []
        self._tasks: set[asyncio.Task[Any]] = set()

    # -- subscription management -------------------------------------------------
    def subscribe(self, handler: Handler) -> None:
        """Register a new subscriber if not already present.

        Args:
            handler: Callable taking an AssistantResponse. May be sync or async.
        """
        if handler in self._subscribers:
            return
        self._subscribers.append(handler)

    def unsubscribe(self, handler: Handler) -> None:
        """Remove a subscriber if present."""
        with suppress(ValueError):
            self._subscribers.remove(handler)

    def reset(self) -> None:
        """Remove all subscribers."""
        self._subscribers.clear()

    # -- publication -------------------------------------------------------------
    def publish(self, event: AssistantResponse) -> None:
        """Publish an event to all current subscribers.

        Scheduling rules:
        - async handlers: scheduled with asyncio.create_task
        - sync handlers: scheduled with loop.call_soon
        """
        # Snapshot to avoid mutation during iteration
        subscribers: Iterable[Handler] = tuple(self._subscribers)
        if not subscribers:
            return

        loop = asyncio.get_running_loop()

        for handler in subscribers:
            try:
                if iscoroutinefunction(handler):
                    # type: ignore[arg-type] - mypy can't detect precise Callable type here
                    task = asyncio.create_task(self._run_async_handler(handler, event))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                else:
                    loop.call_soon(self._run_sync_handler, handler, event)
            except Exception:  # pragma: no cover - defensive path
                logger.exception("Failed to schedule event handler")

    async def drain(self) -> None:
        """Wait for all currently in-flight async handler tasks to finish.

        This method allows tests or shutdown logic to deterministically wait
        until the dispatcher has no more outstanding async handler work.

        Notes:
            - Only waits for tasks that were in-flight at the moment drain is
              called (snapshot semantics). If new events are published during
              the wait, their tasks will not be awaited by this call.
            - Handler exceptions are already logged in their respective
              wrappers; drain does not re-raise them.
        """
        if not self._tasks:
            return
        # Snapshot current tasks to avoid awaiting tasks added after we start
        pending = tuple(self._tasks)
        if not pending:
            return
        # Await each task individually instead of gather so one failure does
        # not cancel the others; failures already logged in handler wrappers.
        for task in pending:
            try:
                await asyncio.shield(task)
            except Exception:  # pragma: no cover - defensive; handler logs already
                # Any exception inside task has already been logged, but we
                # include this safeguard in case of unexpected propagation.
                logger.exception("Unhandled exception while draining task")

    async def _run_async_handler(
        self, handler: Callable[[AssistantResponse], Awaitable[Any]], event: AssistantResponse
    ) -> None:
        try:
            await handler(event)
        except Exception:  # pragma: no cover - handler errors are logged, not raised
            logger.exception("Unhandled exception in async event handler")

    def _run_sync_handler(self, handler: Handler, event: AssistantResponse) -> None:
        try:
            handler(event)
        except Exception:  # pragma: no cover - handler errors are logged, not raised
            logger.exception("Unhandled exception in sync event handler")

    # -- context manager ---------------------------------------------------------
    @asynccontextmanager
    async def subscription(self, handler: Handler) -> AsyncIterator[None]:
        """Async context manager that subscribes on enter and auto-unsubscribes.

        Usage:
            async with dispatcher.subscription(handler):
                ... # receive events
        """
        self.subscribe(handler)
        try:
            yield None
        finally:
            # Ensure cleanup even if the body raises.
            self.unsubscribe(handler)


__all__ = ["EventDispatcher", "Handler"]
