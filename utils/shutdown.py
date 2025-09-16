"""Utilities for managing graceful application shutdown callbacks."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

ShutdownCallback = Callable[[], Awaitable[Any] | Any]

_shutdown_callbacks: list[ShutdownCallback] = []


def register_shutdown_callback(callback: ShutdownCallback) -> None:
    """Register a callback to be invoked during application shutdown.

    Args:
        callback: A zero-argument callable that may be synchronous or
            asynchronous. The callable will be invoked when shutdown callbacks
            are executed.
    """
    _shutdown_callbacks.append(callback)


async def run_shutdown_callbacks() -> None:
    """Execute registered shutdown callbacks in last-in, first-out order."""
    while _shutdown_callbacks:
        callback = _shutdown_callbacks.pop()
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Shutdown callback %r failed", callback)
