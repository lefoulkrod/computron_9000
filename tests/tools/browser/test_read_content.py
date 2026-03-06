"""Tests for the read_page browser tool and _filter_by_query helper."""

from __future__ import annotations

from typing import Any

import pytest

from tools.browser import BrowserToolError
from tools.browser.read_content import _filter_by_query, _READ_BUDGET, read_page
from tests.tools.browser.support.playwright_stubs import StubBrowser, StubPage


def _make_fake_get_active_view(browser: StubBrowser):
    """Build a fake ``get_active_view`` that returns a stub browser + ActiveView."""
    async def _fake(tool_name: str):
        from tools.browser.core.browser import ActiveView
        from tools.browser.core.exceptions import BrowserToolError as BTE
        view = await browser.active_view()
        if view.url in {"", "about:blank"}:
            raise BTE("No open page to read", tool=tool_name)
        return browser, view
    return _fake


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _ReadContentPage(StubPage):
    """StubPage extended with HTML content for read_page tests."""

    def __init__(
        self,
        *,
        title: str = "Test Page",
        html: str = "<body><p>Hello world</p></body>",
        url: str = "https://example.test/article",
    ) -> None:
        super().__init__(title=title, body_text="", url=url)
        self._html = html

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        # Content root JS — return the stored HTML
        if "querySelector" in script and "article" in script:
            return self._html
        # Viewport info query
        if "scroll_top" in script and "scrollY" in script:
            return {
                "scroll_top": 0,
                "viewport_height": 800,
                "viewport_width": 1280,
                "document_height": 2000,
            }
        return await super().evaluate(script, arg)


class _NoSnapshotPage:
    """Page stub with no screenshot capability; events decorator exits early."""


class _NoSnapshotBrowser:
    async def current_page(self) -> _NoSnapshotPage:
        return _NoSnapshotPage()


async def _no_snapshot_get_browser() -> _NoSnapshotBrowser:
    return _NoSnapshotBrowser()


# ---------------------------------------------------------------------------
# _filter_by_query — pure function tests
# ---------------------------------------------------------------------------


class TestFilterByQuery:
    """Tests for the line-level query filtering helper."""

    @pytest.mark.unit
    def test_no_matches_returns_empty(self) -> None:
        """Returns empty string and truncated=False when query not found."""
        content = "Line one\nLine two\nLine three"
        result, truncated = _filter_by_query(content, "missing")
        assert result == ""
        assert truncated is False

    @pytest.mark.unit
    def test_single_match_with_context(self) -> None:
        """Returns matching line with surrounding context lines."""
        lines = ["alpha", "beta", "gamma", "delta", "epsilon"]
        content = "\n".join(lines)
        result, truncated = _filter_by_query(content, "gamma")

        assert truncated is False
        assert "gamma" in result
        assert "beta" in result
        assert "delta" in result
        assert "alpha" not in result

    @pytest.mark.unit
    def test_case_insensitive_matching(self) -> None:
        """Query matching is case-insensitive."""
        content = "Hello World\nfoo bar\nGoodbye"
        result, truncated = _filter_by_query(content, "hello")
        assert "Hello World" in result

    @pytest.mark.unit
    def test_multiple_matches_grouped(self) -> None:
        """Non-adjacent matches are separated by --- delimiters."""
        lines = [
            "match one here",
            "unrelated A",
            "unrelated B",
            "unrelated C",
            "unrelated D",
            "match two here",
        ]
        content = "\n".join(lines)
        result, truncated = _filter_by_query(content, "match")

        assert "match one here" in result
        assert "match two here" in result
        assert "---" in result

    @pytest.mark.unit
    def test_adjacent_matches_merged(self) -> None:
        """Adjacent matches (within context range) are merged into one group."""
        lines = ["alpha", "match A", "match B", "omega"]
        content = "\n".join(lines)
        result, truncated = _filter_by_query(content, "match")

        assert "match A" in result
        assert "match B" in result
        assert "---" not in result

    @pytest.mark.unit
    def test_header_shows_match_count(self) -> None:
        """Result includes a header with match count and total char count."""
        lines = ["match first", "a", "b", "c", "d", "match second"]
        content = "\n".join(lines)
        result, _ = _filter_by_query(content, "match")

        assert '[Filtered for "match"' in result
        assert "2 match(es)" in result

    @pytest.mark.unit
    def test_pagination_returns_next_page(self) -> None:
        """When filtered results exceed budget, page_number=2 gets the rest."""
        lines = []
        for i in range(200):
            lines.append(f"match line {i} " + "x" * 200)
            lines.extend([f"filler {i}a", f"filler {i}b", f"filler {i}c", f"filler {i}d"])

        content = "\n".join(lines)
        page1, truncated1 = _filter_by_query(content, "match", page_number=1)
        assert truncated1 is True
        assert len(page1) > 0

        page2, _ = _filter_by_query(content, "match", page_number=2)
        assert len(page2) > 0
        assert page1 != page2

    @pytest.mark.unit
    def test_page_past_end_returns_empty(self) -> None:
        """Requesting a page number past available results returns empty."""
        content = "one match here"
        result, truncated = _filter_by_query(content, "match", page_number=99)
        assert result == ""
        assert truncated is False


# ---------------------------------------------------------------------------
# read_page — async integration tests with stubbed browser
# ---------------------------------------------------------------------------


class TestReadPage:
    """Tests for the read_page tool function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_string_with_markdown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """read_page returns a formatted string with converted markdown content."""
        page = _ReadContentPage(
            title="My Article",
            html="<body><h1>Title</h1><p>Some content here.</p></body>",
            url="https://example.test/article",
        )
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        result = await read_page()

        assert isinstance(result, str)
        assert "My Article" in result
        assert "https://example.test/article" in result
        assert "Title" in result
        assert "Some content here" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_truncation_on_long_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Content longer than _READ_BUDGET is truncated."""
        long_body = "<p>" + ("word " * 10000) + "</p>"
        page = _ReadContentPage(html=f"<body>{long_body}</body>")
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        result = await read_page()

        assert isinstance(result, str)
        assert "truncated" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_page_number_pagination(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """page_number=2 returns the second chunk of content."""
        paragraphs = "".join(
            f"<p>Paragraph number {i} with unique content.</p>" for i in range(2000)
        )
        page = _ReadContentPage(html=f"<body>{paragraphs}</body>")
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        page1 = await read_page(page_number=1)
        page2 = await read_page(page_number=2)

        assert isinstance(page1, str)
        assert isinstance(page2, str)
        assert "truncated" in page1
        assert page1 != page2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_page_number_past_end_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requesting a page past the end raises BrowserToolError."""
        page = _ReadContentPage(html="<body><p>Short</p></body>")
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        with pytest.raises(BrowserToolError, match="past the end"):
            await read_page(page_number=99)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_page_number_zero_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """page_number < 1 raises BrowserToolError."""
        with pytest.raises(BrowserToolError, match="page_number must be 1"):
            await read_page(page_number=0)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_filters_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """query parameter filters content to matching lines."""
        page = _ReadContentPage(
            html=(
                "<body>"
                "<p>Introduction paragraph</p>"
                "<p>The pricing plan costs $10/month.</p>"
                "<p>Another unrelated paragraph about features.</p>"
                "<p>See pricing details below.</p>"
                "</body>"
            )
        )
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        result = await read_page(query="pricing")

        assert isinstance(result, str)
        assert "pricing" in result.lower()
        assert '[Filtered for "pricing"' in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_no_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """query with no matches returns a 'no matches' message."""
        page = _ReadContentPage(html="<body><p>Hello world</p></body>")
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        result = await read_page(query="nonexistent")

        assert isinstance(result, str)
        assert "No matches" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_browser_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """read_page raises BrowserToolError when no browser is available."""
        from tools.browser.core.exceptions import BrowserToolError as BTE

        async def _raise(tool_name: str):
            raise BTE("No open page to read", tool=tool_name)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _raise)

        with pytest.raises(BrowserToolError, match="No open page"):
            await read_page()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_viewport_info_populated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """read_page includes viewport metadata in the result."""
        page = _ReadContentPage(html="<body><p>Content</p></body>")
        browser = StubBrowser(page)

        monkeypatch.setattr("tools.browser.read_content.get_active_view", _make_fake_get_active_view(browser))

        result = await read_page()

        assert isinstance(result, str)
        assert "Viewport:" in result
