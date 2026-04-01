"""Integration tests for cached tool functions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch, MagicMock

import pytest

from utils.semantic_cache import clear_all_caches

if TYPE_CHECKING:
    from tools.web.types import ReducedWebpage


class TestCachedWebTools:
    """Test that web tools properly cache results."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        """Clear all caches before each test."""
        clear_all_caches()

    @pytest.mark.asyncio
    async def test_get_webpage_caches(self) -> None:
        """get_webpage caches and returns cached for similar URLs."""
        from tools.web.get_webpage import get_webpage

        # Mock the underlying fetch to return consistent content
        mock_html = "<html><body><h1>Test Page</h1><p>This is test content.</p></body></html>"

        with patch("tools.web.get_webpage._get_webpage_raw") as mock_fetch:
            mock_fetch.return_value = MagicMock(html=mock_html)

            # First call
            result1 = await get_webpage("https://example.com/page1")
            assert mock_fetch.call_count == 1

            # Same URL should use cache
            result2 = await get_webpage("https://example.com/page1")
            assert mock_fetch.call_count == 1  # No new fetch

            # Results should be identical
            assert result1.page_text == result2.page_text

    @pytest.mark.asyncio
    async def test_get_webpage_different_urls_fetch(self) -> None:
        """Different URLs should trigger separate fetches."""
        from tools.web.get_webpage import get_webpage

        mock_html1 = "<html><body><h1>Page 1</h1></body></html>"
        mock_html2 = "<html><body><h1>Page 2</h1></body></html>"

        with patch("tools.web.get_webpage._get_webpage_raw") as mock_fetch:
            # Return different content for different URLs
            def side_effect(url: str) -> MagicMock:
                if "page1" in url:
                    return MagicMock(html=mock_html1)
                return MagicMock(html=mock_html2)

            mock_fetch.side_effect = side_effect

            result1 = await get_webpage("https://example.com/page1")
            result2 = await get_webpage("https://example.com/page2")

            assert mock_fetch.call_count == 2
            assert "Page 1" in result1.page_text
            assert "Page 2" in result2.page_text


class TestCachedSearchTools:
    """Test that search tools properly cache results."""

    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        """Clear all caches before each test."""
        clear_all_caches()

    @pytest.mark.asyncio
    async def test_search_google_caches(self) -> None:
        """search_google caches and returns cached for similar queries."""
        from tools.web.search_google import search_google

        mock_results = {
            "items": [
                {"title": "Python Tutorial", "link": "https://python.org", "snippet": "Learn Python"}
            ]
        }

        with patch("tools.web.search_google._perform_request") as mock_perform, \
             patch("tools.web.search_google.os.getenv") as mock_getenv:
            mock_perform.return_value = mock_results
            mock_getenv.return_value = "fake_api_key"

            # First call
            result1 = await search_google("python tutorial")
            assert mock_perform.call_count == 1

            # Similar query should use cache
            result2 = await search_google("python tutorials")
            # With 85% similarity threshold, these should match
            assert mock_perform.call_count == 1  # No new fetch

    @pytest.mark.asyncio
    async def test_search_google_different_queries_fetch(self) -> None:
        """Different queries should trigger separate fetches."""
        from tools.web.search_google import search_google

        mock_results_python = {
            "items": [{"title": "Python", "link": "https://python.org", "snippet": "Python"}]
        }
        mock_results_cooking = {
            "items": [{"title": "Cooking", "link": "https://cooking.com", "snippet": "Cooking"}]
        }

        with patch("tools.web.search_google._perform_request") as mock_perform, \
             patch("tools.web.search_google.os.getenv") as mock_getenv:
            # Return different results for different queries
            def side_effect(*args: object, **kwargs: object) -> dict:
                params = args[2] if len(args) > 2 else kwargs.get("params", {})
                query = params.get("q", "")
                if "python" in query.lower():
                    return mock_results_python
                return mock_results_cooking

            mock_perform.side_effect = side_effect
            mock_getenv.return_value = "fake_api_key"

            result1 = await search_google("python programming")
            result2 = await search_google("cooking recipes")

            # Different queries should result in separate fetches
            assert mock_perform.call_count >= 2
