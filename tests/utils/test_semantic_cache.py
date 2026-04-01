"""Tests for semantic caching utilities."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import numpy as np
import pytest

from utils.semantic_cache import (
    SemanticCache,
    semantic_cached,
    get_metrics,
    clear_all_caches,
    _cosine_similarity,
)


class TestSemanticCache:
    """Test the SemanticCache class."""

    @pytest.mark.asyncio
    async def test_exact_match_returns_cached(self) -> None:
        """Exact argument match returns cached value."""
        cache = SemanticCache()
        await cache.set("arg1", result="result1", ttl=300, kwarg1="val1")

        result = await cache.get("arg1", kwarg1="val1")
        assert result is not None
        assert result.result == "result1"

    @pytest.mark.asyncio
    async def test_semantic_match_finds_similar(self) -> None:
        """Semantically similar arguments find cached value."""
        cache = SemanticCache(similarity_threshold=0.90)
        await cache.set("python tutorial for beginners", result="result1", ttl=300)

        # Similar query should match
        result = await cache.get("beginner python tutorial")
        assert result is not None
        assert result.result == "result1"

    @pytest.mark.asyncio
    async def test_dissimilar_queries_miss(self) -> None:
        """Dissimilar queries should not match."""
        cache = SemanticCache(similarity_threshold=0.95)
        await cache.set("machine learning", result="result1", ttl=300)

        # Different topic should not match
        result = await cache.get("cooking recipes")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self) -> None:
        """Cached entries expire after TTL."""
        cache = SemanticCache()
        await cache.set("arg1", result="result1", ttl=0.1)  # 100ms TTL

        # Should find immediately
        result = await cache.get("arg1")
        assert result is not None

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should be expired
        result = await cache.get("arg1")
        assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self) -> None:
        """Oldest entries evicted when maxsize reached."""
        cache = SemanticCache(maxsize=2)
        await cache.set("arg1", result="result1", ttl=300)
        await cache.set("arg2", result="result2", ttl=300)
        await cache.set("arg3", result="result3", ttl=300)  # Should evict arg1

        assert len(cache._semantic_entries) == 2
        assert "arg1" not in [e for e in cache._semantic_entries]

    @pytest.mark.asyncio
    async def test_clear_removes_all(self) -> None:
        """Clear removes all cached entries."""
        cache = SemanticCache()
        await cache.set("arg1", result="result1", ttl=300)
        await cache.set("arg2", result="result2", ttl=300)

        await cache.clear()

        assert len(cache._semantic_entries) == 0
        assert len(cache._exact_cache) == 0


class TestSemanticCachedDecorator:
    """Test the @semantic_cached decorator."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> None:
        """Clear caches before and after each test."""
        clear_all_caches()
        yield
        clear_all_caches()

    @pytest.mark.asyncio
    async def test_decorator_caches_results(self) -> None:
        """Decorator caches function results."""
        calls = 0

        @semantic_cached(ttl=300)
        async def test_func(query: str) -> str:
            nonlocal calls
            calls += 1
            return f"result for {query}"

        # First call should execute
        result1 = await test_func("test query")
        assert calls == 1
        assert result1 == "result for test query"

        # Second call with same args should hit cache
        result2 = await test_func("test query")
        assert calls == 1  # No new execution
        assert result2 == "result for test query"

    @pytest.mark.asyncio
    async def test_decorator_semantic_matching(self) -> None:
        """Decorator matches semantically similar queries."""
        calls = 0

        @semantic_cached(ttl=300, similarity_threshold=0.90)
        async def search(query: str) -> str:
            nonlocal calls
            calls += 1
            return f"results for {query}"

        await search("python programming")
        assert calls == 1

        # Similar query should use cache
        result = await search("programming in python")
        assert calls == 1  # Still cached
        assert result == "results for python programming"

    @pytest.mark.asyncio
    async def test_decorator_clear_cache(self) -> None:
        """Decorator clear_cache method works."""
        calls = 0

        @semantic_cached(ttl=300)
        async def test_func(x: int) -> int:
            nonlocal calls
            calls += 1
            return x * 2

        await test_func(5)
        await test_func(5)
        assert calls == 1

        await test_func.clear_cache()

        await test_func(5)
        assert calls == 2  # Cache was cleared

    @pytest.mark.asyncio
    async def test_decorator_get_stats(self) -> None:
        """Decorator get_stats method returns cache stats."""
        @semantic_cached(ttl=300, maxsize=100)
        async def test_func(x: int) -> int:
            return x * 2

        await test_func(5)
        await test_func(10)

        stats = test_func.get_stats()
        assert stats["size"] == 2
        assert stats["maxsize"] == 100


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        assert _cosine_similarity(a, a) == pytest.approx(1.0)

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0)


class TestCacheStats:
    """Test cache statistics."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> None:
        """Clear caches before and after each test."""
        clear_all_caches()
        yield
        clear_all_caches()

    @pytest.mark.asyncio
    async def test_stats_reporting(self) -> None:
        """Cache reports accurate statistics."""
        cache = SemanticCache(maxsize=100)
        await cache.set("a1", result="r1", ttl=300)
        await cache.set("a2", result="r2", ttl=300)

        stats = cache.get_stats()
        assert stats["size"] == 2
        assert stats["maxsize"] == 100


class TestGetMetrics:
    """Test global metrics retrieval."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> None:
        """Clear caches before and after each test."""
        clear_all_caches()
        yield
        clear_all_caches()

    @pytest.mark.asyncio
    async def test_get_all_metrics(self) -> None:
        """Get metrics returns all function metrics."""
        @semantic_cached(ttl=300)
        async def func1(x: int) -> int:
            return x

        @semantic_cached(ttl=300)
        async def func2(x: str) -> str:
            return x

        await func1(1)
        await func2("a")

        all_metrics = get_metrics()
        assert len(all_metrics) >= 2

    def test_get_specific_metrics(self) -> None:
        """Get metrics can return specific function metrics."""
        metrics = get_metrics("nonexistent.function")
        assert metrics == {}
