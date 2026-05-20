"""Tests for tools.misc.search_web."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.misc.search_web import _MAX_RESULTS, _RESULT_BUDGET, _run_search, search_web

_FAKE_RESULTS = [
    {"title": "Result One", "href": "https://example.com/1", "body": "Snippet one."},
    {"title": "Result Two", "href": "https://example.com/2", "body": "Snippet two."},
]


def _patch_run_search(return_value: list[dict[str, str]]):
    return patch(
        "tools.misc.search_web._run_search",
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# _run_search (sync helper)
# ---------------------------------------------------------------------------


def test_run_search_uses_context_manager():
    """_run_search opens DDGS as a context manager and calls .text()."""
    mock_ddgs = MagicMock()
    mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
    mock_ddgs.__exit__ = MagicMock(return_value=False)
    mock_ddgs.text.return_value = iter(_FAKE_RESULTS)

    with patch("tools.misc.search_web.DDGS", return_value=mock_ddgs):
        results = _run_search("python", 3)

    mock_ddgs.__enter__.assert_called_once()
    mock_ddgs.__exit__.assert_called_once()
    mock_ddgs.text.assert_called_once_with("python", max_results=3)
    assert results == _FAKE_RESULTS


# ---------------------------------------------------------------------------
# search_web (async public API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_web_formats_results():
    """Normal results are formatted with index, title, URL, and snippet."""
    with _patch_run_search(_FAKE_RESULTS):
        output = await search_web("python")

    assert "Result One" in output
    assert "https://example.com/1" in output
    assert "Snippet one." in output
    assert "Result Two" in output
    assert "1." in output
    assert "2." in output


@pytest.mark.asyncio
async def test_search_web_no_results():
    """Empty result list returns a plain 'no results' message."""
    with _patch_run_search([]):
        output = await search_web("xyzzy nothing here")

    assert "No results found" in output
    assert "xyzzy nothing here" in output


@pytest.mark.asyncio
async def test_search_web_raises_on_error():
    """A failure from _run_search is re-raised as RuntimeError."""
    with patch(
        "tools.misc.search_web._run_search", side_effect=Exception("timeout")
    ):
        with pytest.raises(RuntimeError, match="Search failed"):
            await search_web("python")


@pytest.mark.asyncio
async def test_search_web_truncates_long_output():
    """Output longer than _RESULT_BUDGET is cut and marked [truncated]."""
    long_snippet = "x" * _RESULT_BUDGET
    big_results = [
        {"title": "Big", "href": "https://example.com", "body": long_snippet}
    ]
    with _patch_run_search(big_results):
        output = await search_web("big")

    assert len(output) <= _RESULT_BUDGET + len("\n[truncated]")
    assert output.endswith("[truncated]")


@pytest.mark.asyncio
async def test_search_web_clamps_max_results_high():
    """max_results above the cap is silently clamped to _MAX_RESULTS."""
    with _patch_run_search(_FAKE_RESULTS) as mock:
        await search_web("python", max_results=999)

    mock.assert_called_once_with("python", _MAX_RESULTS)


@pytest.mark.asyncio
async def test_search_web_clamps_max_results_low():
    """max_results below 1 is silently clamped to 1."""
    with _patch_run_search(_FAKE_RESULTS) as mock:
        await search_web("python", max_results=0)

    mock.assert_called_once_with("python", 1)


@pytest.mark.asyncio
async def test_search_web_result_missing_fields():
    """Results with missing fields degrade gracefully (no KeyError)."""
    sparse = [{"title": "Only title", "href": "", "body": ""}]
    with _patch_run_search(sparse):
        output = await search_web("sparse")

    assert "Only title" in output
