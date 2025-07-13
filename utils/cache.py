import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import cachetools
from cachetools.keys import hashkey

logger = logging.getLogger(__name__)

# Module-level cache registry
_cache_registry: dict[str, cachetools.LRUCache] = {}


def async_lru_cache(maxsize: int = 10) -> Callable:
    """
    Decorator to cache async function results using cachetools. If no cache is provided, creates one per function.

    Args:
        maxsize (int): Maximum size of the LRU cache. Default is 10.

    Returns:
        Callable: Decorated async function.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        cache_key = f"{func.__module__}.{func.__qualname__}"
        if cache_key not in _cache_registry:
            _cache_registry[cache_key] = cachetools.LRUCache(maxsize=maxsize)
        cache = _cache_registry[cache_key]

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = hashkey(*args, **kwargs)
            if key in cache:
                logger.debug(f"Cache hit for {cache_key} key: {key}")
                return cache[key]
            logger.debug(f"Cache miss for {cache_key} key: {key}")
            result = await func(*args, **kwargs)
            cache[key] = result
            return result

        return wrapper

    return decorator
