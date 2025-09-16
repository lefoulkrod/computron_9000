"""Utilities for Computron 9000.

This package provides utility functions such as async LRU caching and completion generation.

"""

from .cache import async_lru_cache
from .shutdown import register_shutdown

__all__ = [
    "async_lru_cache",
    "register_shutdown",
]
