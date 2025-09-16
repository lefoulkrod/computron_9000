"""Integration tests for the live Google search web tool.

These tests hit the real Google Custom Search API and therefore require
the following environment variables (can be set in a local .env file):

- GOOGLE_SEARCH_API_KEY
- GOOGLE_SEARCH_ENGINE_ID

They are marked as integration and will be skipped automatically if the
required environment variables are not available.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from config import load_config
from tools.web.search_google import GoogleSearchError, GoogleSearchResults, search_google


@pytest.mark.integration
def test_search_google_live_returns_results() -> None:
    """Call the live API and assert we get at least one valid result.

    Skips if required environment variables are not set.
    """
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    if not api_key or not engine_id:
        pytest.skip(
            "Missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID; skipping live test.",
        )

    # Ensure any cached config (which reads env-driven defaults) is reset
    load_config.cache_clear()

    # Use a lightweight query and small result count to keep the test fast and deterministic
    try:
        results = asyncio.run(search_google("site:python.org asyncio", max_results=2))
    except GoogleSearchError as exc:
        # If the API key/engine is invalid or not enabled for Custom Search, skip.
        msg = str(exc).lower()
        known_setup_issues = (
            "invalid key",
            "invalid argument",
            "forbidden",
            "daily limit exceeded",
            "missing required parameter",
            "access not configured",
            "keyless access to api is blocked",
        )
        if any(s in msg for s in known_setup_issues):
            pytest.skip(f"Google Search not properly configured for tests: {exc}")
        # Unknown runtime issue — re-raise to surface a real failure
        raise

    assert isinstance(results, GoogleSearchResults)
    assert len(results.results) >= 1
    # Basic shape validation
    for item in results.results:
        assert item.link.startswith("http")
        assert isinstance(item.title, str) and item.title.strip() != ""
