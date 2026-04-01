"""Semantic cache for tool results with embedding-based similarity matching.

This module provides intelligent caching for tool results based on semantic
similarity rather than exact string matching. It uses sentence-transformers
to generate embeddings and cosine similarity to find similar queries.

Example:
    @semantic_cached(ttl=600, similarity_threshold=0.90)
    async def search_web(query: str) -> dict:
        # This will cache results and return cached for similar queries
        return await fetch_results(query)
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import numpy as np

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# Global model instance (lazy loaded)
_model: Any | None = None


def _get_model() -> Any:
    """Lazy-load the embedding model.

    Returns:
        The sentence-transformers model instance.
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            # Use lightweight model suitable for semantic similarity
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded sentence-transformers model: all-MiniLM-L6-v2")
        except ImportError as exc:
            logger.exception("Failed to load sentence-transformers")
            raise ImportError(
                "sentence-transformers is required for semantic caching. "
                "Install with: pip install sentence-transformers"
            ) from exc
    return _model


def _compute_embedding(text: str) -> np.ndarray:
    """Compute embedding for text.

    Args:
        text: The text to encode.

    Returns:
        The embedding vector as a numpy array.
    """
    model = _get_model()
    return model.encode(text, convert_to_numpy=True)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity value between -1 and 1.
    """
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@dataclass
class CachedEntry:
    """A cached result with metadata.

    Attributes:
        key_hash: Exact key hash for fast lookup.
        embedding: Semantic embedding for similarity matching.
        result: The cached result.
        timestamp: When the entry was cached.
        ttl: TTL in seconds.
        access_count: Number of times this entry was accessed.
        last_accessed: Timestamp of last access.
    """

    key_hash: str
    embedding: np.ndarray
    result: Any
    timestamp: float
    ttl: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if the cached entry has expired.

        Returns:
            True if the entry is expired, False otherwise.
        """
        return time.time() - self.timestamp > self.ttl


class SemanticCache:
    """In-memory semantic cache with TTL and LRU eviction.

    This cache supports both exact matching (via hash) and semantic matching
    (via cosine similarity of embeddings).

    Attributes:
        maxsize: Maximum number of cached entries.
        default_ttl: Default TTL in seconds.
        similarity_threshold: Cosine similarity threshold for semantic matching.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        default_ttl: float = 300.0,
        similarity_threshold: float = 0.92,
    ) -> None:
        """Initialize the semantic cache.

        Args:
            maxsize: Maximum number of cached entries.
            default_ttl: Default TTL in seconds.
            similarity_threshold: Cosine similarity threshold (0-1).
        """
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.similarity_threshold = similarity_threshold
        self._exact_cache: dict[str, CachedEntry] = {}
        self._semantic_entries: list[CachedEntry] = []
        self._lock = asyncio.Lock()

    def _compute_key_hash(self, *args: Any, **kwargs: Any) -> str:
        """Compute hash key for exact matching.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            SHA-256 hash of the serialized arguments.
        """
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _compute_embedding(self, *args: Any, **kwargs: Any) -> np.ndarray:
        """Compute embedding for semantic matching.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Embedding vector for the arguments.
        """
        key_text = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return _compute_embedding(key_text)

    async def get(self, *args: Any, **kwargs: Any) -> CachedEntry | None:
        """Get cached entry by exact or semantic match.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The cached entry if found, None otherwise.
        """
        async with self._lock:
            key_hash = self._compute_key_hash(*args, **kwargs)

            # Try exact match first
            if key_hash in self._exact_cache:
                entry = self._exact_cache[key_hash]
                if not entry.is_expired():
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    logger.debug("Exact cache hit for key: %s", key_hash[:8])
                    return entry
                # Remove expired entry
                del self._exact_cache[key_hash]
                self._semantic_entries = [e for e in self._semantic_entries if e.key_hash != key_hash]

            # Try semantic match
            query_embedding = self._compute_embedding(*args, **kwargs)
            best_match: CachedEntry | None = None
            best_similarity = 0.0

            for entry in self._semantic_entries:
                if entry.is_expired():
                    continue
                similarity = _cosine_similarity(query_embedding, entry.embedding)
                if similarity > self.similarity_threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry

            if best_match:
                best_match.access_count += 1
                best_match.last_accessed = time.time()
                logger.debug("Semantic cache hit with similarity %.3f", best_similarity)

            return best_match

    async def set(self, *args: Any, result: Any = None, ttl: float | None = None, **kwargs: Any) -> None:
        """Store result in cache.

        Args:
            *args: Positional arguments used as cache key.
            result: The result to cache.
            ttl: Optional TTL override in seconds.
            **kwargs: Keyword arguments used as cache key.
        """
        async with self._lock:
            key_hash = self._compute_key_hash(*args, **kwargs)
            embedding = self._compute_embedding(*args, **kwargs)

            entry = CachedEntry(
                key_hash=key_hash,
                embedding=embedding,
                result=result,
                timestamp=time.time(),
                ttl=ttl or self.default_ttl,
            )

            self._exact_cache[key_hash] = entry
            self._semantic_entries.append(entry)

            # LRU eviction if over size
            if len(self._semantic_entries) > self.maxsize:
                self._semantic_entries.sort(key=lambda e: (e.access_count, e.last_accessed))
                removed = self._semantic_entries.pop(0)
                if removed.key_hash in self._exact_cache:
                    del self._exact_cache[removed.key_hash]
                logger.debug("Evicted cache entry with key: %s", removed.key_hash[:8])

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._exact_cache.clear()
            self._semantic_entries.clear()
            logger.debug("Cleared all cache entries")

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "size": len(self._semantic_entries),
            "maxsize": self.maxsize,
            "exact_hits": sum(1 for e in self._semantic_entries if e.access_count > 0),
        }


# Registry of caches per function
_cache_registry: dict[str, SemanticCache] = {}
_metrics_registry: dict[str, dict[str, int]] = {}


def get_cache(func_name: str) -> SemanticCache:
    """Get or create cache for a function.

    Args:
        func_name: The fully qualified function name.

    Returns:
        The SemanticCache instance for the function.
    """
    if func_name not in _cache_registry:
        _cache_registry[func_name] = SemanticCache()
        _metrics_registry[func_name] = {"hits": 0, "misses": 0, "semantic_hits": 0}
    return _cache_registry[func_name]


def get_metrics(func_name: str | None = None) -> dict[str, Any]:
    """Get cache metrics for all or specific function.

    Args:
        func_name: Optional function name to get metrics for.

    Returns:
        Dictionary of metrics.
    """
    if func_name:
        return _metrics_registry.get(func_name, {})
    return _metrics_registry.copy()


def clear_all_caches() -> None:
    """Clear all semantic caches synchronously."""
    for cache in _cache_registry.values():
        cache._exact_cache.clear()
        cache._semantic_entries.clear()
    _metrics_registry.clear()
    logger.info("Cleared all semantic caches")


def semantic_cached(
    ttl: float = 300.0,
    similarity_threshold: float = 0.92,
    maxsize: int = 1000,
    key_func: Any | None = None,
    invalidate_on: list[str] | None = None,
) -> Any:
    """Decorator for semantic caching of async functions.

    This decorator caches function results based on semantic similarity of
    arguments. Similar queries (e.g., "python tutorial" and "tutorials for python")
    will share cached results.

    Args:
        ttl: Time-to-live in seconds for cached entries.
        similarity_threshold: Cosine similarity threshold for semantic matching (0-1).
        maxsize: Maximum number of cached entries.
        key_func: Optional function to extract cache key from arguments.
        invalidate_on: List of file paths; cache invalidated when files change.

    Returns:
        Decorated async function with cache management methods attached.

    Example:
        @semantic_cached(ttl=600, similarity_threshold=0.90)
        async def search_web(query: str) -> dict:
            return await fetch_results(query)
    """

    def decorator(func: Any) -> Any:
        cache_key = f"{func.__module__}.{func.__qualname__}"
        cache = SemanticCache(maxsize=maxsize, default_ttl=ttl, similarity_threshold=similarity_threshold)
        _cache_registry[cache_key] = cache

        if cache_key not in _metrics_registry:
            _metrics_registry[cache_key] = {"hits": 0, "misses": 0, "semantic_hits": 0}

        # Track file modification times for invalidation
        file_mtimes: dict[str, float] = {}
        if invalidate_on:
            for path in invalidate_on:
                try:
                    file_mtimes[path] = Path(path).stat().st_mtime
                except OSError:
                    pass

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Check if files changed (invalidate cache)
            if invalidate_on:
                for path in invalidate_on:
                    try:
                        mtime = Path(path).stat().st_mtime
                        if file_mtimes.get(path) != mtime:
                            await cache.clear()
                            file_mtimes[path] = mtime
                            break
                    except OSError:
                        pass

            # Check cache
            cached = await cache.get(*args, **kwargs)
            if cached is not None:
                _metrics_registry[cache_key]["hits"] += 1
                return cached.result

            # Execute and cache
            _metrics_registry[cache_key]["misses"] += 1
            result = await func(*args, **kwargs)
            await cache.set(result, ttl, *args, **kwargs)
            return result

        # Attach cache management methods
        wrapper.cache = cache  # type: ignore[attr-defined]
        wrapper.clear_cache = cache.clear  # type: ignore[attr-defined]
        wrapper.get_stats = cache.get_stats  # type: ignore[attr-defined]

        return wrapper

    return decorator
