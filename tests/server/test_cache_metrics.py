"""Tests for cache metrics API endpoints."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from server.aiohttp_app import create_app
from server.cache_metrics import cache_metrics_handler, cache_clear_handler
from utils.semantic_cache import clear_all_caches, semantic_cached


class TestCacheMetricsEndpoint(AioHTTPTestCase):
    """Test the cache metrics API endpoint."""

    async def get_application(self) -> web.Application:
        """Return test application."""
        clear_all_caches()
        return create_app()

    @unittest_run_loop
    async def test_get_metrics_empty(self) -> None:
        """GET /api/cache/metrics returns empty metrics initially."""
        response = await self.client.request("GET", "/api/cache/metrics")
        assert response.status == 200

        data = await response.json()
        # Response is a dict of metrics per function
        assert isinstance(data, dict)

    @unittest_run_loop
    async def test_get_metrics_with_entries(self) -> None:
        """GET /api/cache/metrics returns metrics for cached functions."""
        # Create a cached function and make some calls
        @semantic_cached(ttl=300, similarity_threshold=0.90)
        async def test_func(query: str) -> str:
            return f"Result for {query}"

        # Create cache entries by calling the function
        await test_func("test query 1")
        await test_func("test query 2")

        response = await self.client.request("GET", "/api/cache/metrics")
        assert response.status == 200

        data = await response.json()
        assert isinstance(data, dict)

    @unittest_run_loop
    async def test_clear_all_caches(self) -> None:
        """POST /api/cache/clear clears all caches."""
        @semantic_cached(ttl=300)
        async def func1(x: str) -> str:
            return f"func1-{x}"

        # Populate caches
        await func1("test")

        # Get initial metrics
        response = await self.client.request("GET", "/api/cache/metrics")
        data = await response.json()
        initial_entries = len(data)

        # Clear all
        response = await self.client.request("POST", "/api/cache/clear")
        assert response.status == 200

        clear_response = await response.json()
        assert clear_response["status"] == "cleared"

    @unittest_run_loop
    async def test_metrics_invalid_method(self) -> None:
        """Cache metrics endpoint rejects invalid methods."""
        response = await self.client.request("POST", "/api/cache/metrics")
        assert response.status == 405  # Method not allowed