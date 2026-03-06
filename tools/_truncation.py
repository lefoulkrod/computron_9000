"""Decorator for marking tool arguments that should be truncated in message history.

This module is intentionally dependency-free (no imports from ``agents``) so
that tool modules can import it without creating circular dependencies.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

# Attribute name set on decorated functions.
TRUNCATE_ATTR = "_truncate_args"


def truncate_args(**thresholds: int) -> Callable[..., Any]:
    """Mark tool function parameters for truncation in message history.

    Each keyword maps a parameter name to a character threshold.  When the
    tool call is stored in message history, string arguments longer than the
    threshold are replaced with a short placeholder indicating the original
    size.  A threshold of ``0`` means the value is always replaced.

    Example::

        @truncate_args(content=0, cmd=500)
        async def write_file(path: str, content: str) -> ...:
            ...

    Args:
        **thresholds: Mapping of parameter names to max character counts.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Use an async wrapper for coroutine functions so that
        # inspect.iscoroutinefunction() still returns True.
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)

            setattr(async_wrapper, TRUNCATE_ATTR, thresholds)
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        setattr(wrapper, TRUNCATE_ATTR, thresholds)
        return wrapper

    return decorator
