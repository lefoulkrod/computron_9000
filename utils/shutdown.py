"""Global shutdown registry with async support and signal/atexit hooks.

This module provides a lightweight registry so packages can register cleanup
callbacks that will be invoked when the process is shutting down.

Features:
- Register sync or async functions with optional priority and name.
- Idempotent execution: shutdown runs at most once.
- Integrated with SIGINT/SIGTERM and atexit.
- Exceptions in one handler don't prevent others.

Usage:
    from utils.shutdown import register_shutdown

    async def close_something():
        ...

    register_shutdown(close_something, name="close_something", priority=10)
    # Shutdown runs automatically on SIGINT/SIGTERM or interpreter exit.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import signal
import threading
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # Imported for typing only
    from types import FrameType

logger = logging.getLogger(__name__)


Callback = Callable[[], Any] | Callable[[], Awaitable[Any]]


@dataclass(frozen=True)
class _Entry:
    priority: int
    name: str
    func: Callback


_handlers: list[_Entry] = []
_names: set[str] = set()
_lock = threading.Lock()
_ran = False
_installed_hooks = False


def _ensure_hooks_installed() -> None:
    """Install signal and atexit hooks once.

    This is safe to call multiple times; hooks are installed only once.
    """
    global _installed_hooks  # noqa: PLW0603
    with _lock:
        if _installed_hooks:
            return
        _installed_hooks = True

    # Register SIGINT and SIGTERM handlers
    def _on_signal(signum: int, _frame: FrameType | None) -> None:  # pragma: no cover - signal path
        logger.info("Received signal %s, triggering shutdown", signum)
        try:
            _trigger_shutdown(block=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Error during shutdown on signal %s", signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, RuntimeError):  # pragma: no cover - platform differences
            logger.debug("Skipping signal hook for %s", sig)

    # atexit fallback
    atexit.register(lambda: _trigger_shutdown(block=True))


def register_shutdown(func: Callback, *, name: str | None = None, priority: int = 0) -> str:
    """Register a shutdown callback.

    Args:
        func: The callback to invoke during shutdown. May be sync or async.
        name: Optional unique name. If omitted, derived from function name.
        priority: Higher runs earlier. Callbacks are executed in descending order.

    Returns:
        The unique name under which the callback was registered.
    """
    _ensure_hooks_installed()
    base = name or getattr(func, "__name__", "callback") or "callback"
    unique = base
    with _lock:
        suffix = 1
        while unique in _names:
            suffix += 1
            unique = f"{base}_{suffix}"
        entry = _Entry(priority=priority, name=unique, func=func)
        _handlers.append(entry)
        _names.add(unique)
    logger.debug("Registered shutdown callback '%s' (priority=%s)", unique, priority)
    return unique


def _unregister_shutdown(name_or_func: str | Callback) -> bool:
    """Unregister a previously registered shutdown callback.

    Args:
        name_or_func: The unique name or the function object to remove.

    Returns:
        True if a callback was removed; False otherwise.
    """
    removed = False
    with _lock:
        global _handlers  # noqa: PLW0603
        new_list: list[_Entry] = []
        for e in _handlers:
            if isinstance(name_or_func, str):
                match = e.name == name_or_func
            else:
                match = e.func is name_or_func
            if match:
                _names.discard(e.name)
                removed = True
            else:
                new_list.append(e)
        _handlers = new_list
    if removed:
        logger.debug("Unregistered shutdown callback '%s'", name_or_func)
    return removed


async def _run_shutdown_handlers() -> None:
    """Run all registered shutdown handlers exactly once.

    Handlers are executed in order of descending priority. If multiple handlers
    have the same priority, their relative order corresponds to registration
    order. Exceptions are logged and do not stop subsequent handlers.
    """
    global _ran  # noqa: PLW0603
    with _lock:
        if _ran:
            return
        _ran = True

        # Snapshot handlers and clear registry to avoid re-runs
        entries: Iterable[_Entry] = sorted(_handlers, key=lambda e: e.priority, reverse=True)
        _handlers.clear()
        _names.clear()

    for entry in entries:
        try:
            res = entry.func()
            if asyncio.iscoroutine(res):
                await res  # type: ignore[func-returns-value]
        except Exception:
            logger.exception("Shutdown callback '%s' failed", entry.name)


def _trigger_shutdown(*, block: bool = True, timeout: float | None = None) -> None:
    """Trigger shutdown handler execution from synchronous code.

    If called within a signal or other synchronous path, handlers (including
    async ones) will be executed in a background thread using ``asyncio.run``.

    Args:
        block: Whether to block until all handlers complete.
        timeout: Optional seconds to wait when ``block`` is True. ``None`` means
            wait indefinitely.
    """
    with _lock:
        if _ran:
            logger.debug("Shutdown already executed; skipping trigger")
            return

    def _runner() -> None:
        try:
            asyncio.run(_run_shutdown_handlers())
        except Exception:  # pragma: no cover - defensive
            logger.exception("Unexpected error while running shutdown handlers")

    thread = threading.Thread(target=_runner, name="shutdown-runner", daemon=True)
    thread.start()
    if block:
        thread.join(timeout=timeout)
        if thread.is_alive():  # pragma: no cover - timing dependent
            logger.warning("Shutdown handlers did not finish within timeout")


def _shutdown_has_run() -> bool:
    """Return True if shutdown has already executed."""
    with _lock:
        return _ran


def _registered_callbacks() -> list[str]:
    """Return the list of currently registered callback names."""
    with _lock:
        return [e.name for e in _handlers]


# Note: No test-only helpers are exposed here. Tests should use their own
# fixtures to isolate global state without importing private helpers.
