import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import cachetools
from cachetools.keys import hashkey

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

# Module-level cache registry
_cache_registry: dict[str, cachetools.LRUCache[Any, Any]] = {}


def async_lru_cache(
    maxsize: int = 10,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to cache async function results using cachetools.

    If no cache is provided, creates one per function.

    Args:
        maxsize (int): Maximum size of the LRU cache. Default is 10.

    Returns:
        Callable: Decorated async function.

    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        cache_key = f"{func.__module__}.{func.__qualname__}"
        if cache_key not in _cache_registry:
            _cache_registry[cache_key] = cachetools.LRUCache(maxsize=maxsize)
        cache = _cache_registry[cache_key]

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = hashkey(*args, **kwargs)
            if key in cache:
                logger.debug("Cache hit for %s key: %r", cache_key, key)
                return cache[key]
            logger.debug("Cache miss for %s key: %r", cache_key, key)
            result = await func(*args, **kwargs)
            cache[key] = result
            return result

        return wrapper

    return decorator
