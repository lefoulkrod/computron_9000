"""Async LRU cache utilities.

Provides a time-based cache decorator for coroutine functions using
cachetools.TTLCache. The decorator enforces that function arguments are
hashable and stores results in a per-function TTL cache (default 60s).
"""

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import cachetools
from cachetools.keys import hashkey

P = ParamSpec("P")
R = TypeVar("R", covariant=True)

logger = logging.getLogger(__name__)

# Module-level cache registry (supports multiple cache types)
_cache_registry: dict[str, cachetools.Cache[Any, Any]] = {}
"""Registry mapping function keys to their cachetools cache instances."""

# Tracks in-progress computations per function cache_key -> dict[key, Future]
_in_progress: dict[str, dict[Any, "asyncio.Future[Any]"]] = {}


def clear_cache(func: Callable[..., Any]) -> None:
    """Clear the cache for a decorated function (used by tests).

    Args:
        func: The original function object (the decorated wrapper or the
            underlying function). If the wrapper is passed, the function's
            module and qualname are used to locate the cache.
    """
    cache_key = f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"
    if cache_key in _cache_registry:
        _cache_registry[cache_key].clear()


def async_lru_cache(
    ttl: float = 60.0,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to cache async function results using cachetools.

    Only hashable positional and keyword arguments are supported.
    If any argument is not hashable, a TypeError is raised.

    Args:
        maxsize (int): Maximum size of the LRU cache. Default is 10.
        ttl (float | None): Optional time-to-live in seconds for cache entries.
            If provided and > 0, entries expire after `ttl` seconds. If None or
            <= 0, only LRU-based eviction is used.

    Returns:
        Callable: Decorated async function.

    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        cache_key = f"{func.__module__}.{func.__qualname__}"
        # Use a TTLCache with a single slot (only cache the last value for a
        # given argument key). TTL defaults to 60s.
        if cache_key not in _cache_registry:
            _cache_registry[cache_key] = cachetools.TTLCache(maxsize=1, ttl=ttl)
        cache = _cache_registry[cache_key]

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            # Build the cachetools key and ensure it is hashable
            key = hashkey(*args, **kwargs)
            try:
                hash(key)
            except TypeError as exc:  # pragma: no cover - defensive
                raise TypeError("Arguments to async_lru_cache must be hashable") from exc

            # Return cached value if present
            if key in cache:
                logger.debug("Cache hit for %s key: %r", cache_key, key)
                cached_value = cache[key]
                from typing import cast

                return cast(R, cached_value)

            # Ensure there's an in-progress map for this function
            inprog = _in_progress.setdefault(cache_key, {})

            # If a computation for this key is already in progress, await it
            if key in inprog:
                logger.debug("Awaiting in-progress computation for %s key: %r", cache_key, key)
                existing_fut = inprog[key]
                # existing_fut is an asyncio.Future that will hold an R
                result_from_existing = await existing_fut
                from typing import cast

                return cast(R, result_from_existing)

            # Otherwise, create a future and compute the value
            new_fut: asyncio.Future[R] = asyncio.get_running_loop().create_future()
            inprog[key] = new_fut
            try:
                logger.debug("Cache miss (compute) for %s key: %r", cache_key, key)
                result: R = await func(*args, **kwargs)
                cache[key] = result
                # Complete the future so waiting coroutines receive the result
                if not new_fut.done():
                    new_fut.set_result(result)
                return result
            except Exception as exc:  # ensure waiting coroutines get the exception
                if not new_fut.done():
                    new_fut.set_exception(exc)
                raise
            finally:
                # Clean up in-progress map
                inprog.pop(key, None)

        return wrapper

    return decorator
