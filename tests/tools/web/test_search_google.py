"""Tests for the Google search web tool."""

from __future__ import annotations

import asyncio
import importlib
from typing import Iterator

import pytest

from config import load_config
from tools.web.search_google import (
    GoogleSearchError,
    GoogleSearchResults,
    search_google,
)

# Explicitly import the submodule to obtain the module object for monkeypatching.
search_module = importlib.import_module("tools.web.search_google")


@pytest.fixture(autouse=True)
def clear_config_cache() -> Iterator[None]:
    """Ensure configuration cache does not leak between tests."""

    load_config.cache_clear()
    yield
    load_config.cache_clear()


def test_search_google_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool should raise an error when the API key is missing."""

    monkeypatch.delenv("GOOGLE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)

    with pytest.raises(GoogleSearchError) as exc:
        asyncio.run(search_google("python", max_results=1))

    assert "GOOGLE_SEARCH_API_KEY" in str(exc.value)


def test_search_google_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful responses should be converted into typed results."""

    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_SEARCH_ENGINE_ID", "engine-id")

    responses = [
        {
            "items": [
                {
                    "title": "Result One",
                    "link": "https://example.com/1",
                    "snippet": "First snippet",
                },
                {
                    "title": "Result Two",
                    "link": "https://example.com/2",
                    "htmlSnippet": "Second snippet",
                },
            ],
            "queries": {"nextPage": [{"startIndex": 11}]},
        },
    ]

    async def fake_perform(
        session,  # type: ignore[unused-argument]
        endpoint: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        assert endpoint == "https://www.googleapis.com/customsearch/v1"
        assert params["q"] == "python testing"
        assert params["num"] == 2
        assert params["cx"] == "engine-id"
        return responses.pop(0)

    monkeypatch.setattr(search_module, "_perform_request", fake_perform)

    result = asyncio.run(search_google("python testing", max_results=2))

    assert isinstance(result, GoogleSearchResults)
    assert len(result.results) == 2
    assert result.results[0].title == "Result One"
    assert result.results[0].snippet == "First snippet"
    assert result.results[1].link == "https://example.com/2"
    assert result.results[1].snippet == "Second snippet"


def test_search_google_missing_engine_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a helpful error when the engine identifier is absent."""

    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)

    async def fake_perform(
        session,  # type: ignore[unused-argument]
        endpoint: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        raise GoogleSearchError("Missing required parameter: cx")

    monkeypatch.setattr(search_module, "_perform_request", fake_perform)

    with pytest.raises(GoogleSearchError) as exc:
        asyncio.run(search_google("python", max_results=1))

    message = str(exc.value)
    assert "GOOGLE_SEARCH_ENGINE_ID" in message or "search_google tool settings" in message
