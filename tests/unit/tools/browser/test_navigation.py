"""Unit tests for goto / new_tab / close_tab."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tools.browser import BrowserToolError, close_tab, goto, new_tab
from tools.browser.core.browser import ActiveView, BrowserInteractionResult
from tools.browser.core.page_view import PageView


class _StubPage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True


class _StubBrowser:
    """Browser stub modeling stable IDs + busy flag + open_tabs."""

    def __init__(self) -> None:
        self._pages: list[_StubPage] = []
        self._ids: dict[_StubPage, int] = {}
        self._next_id = 0
        self._pages_in_navigation: set[_StubPage] = set()

    # ── Tab tracking ──────────────────────────────────────────────────
    def open_tabs(self) -> list[_StubPage]:
        return [p for p in self._pages if not p.is_closed()]

    def tab_id_of(self, page: _StubPage) -> int | None:
        return self._ids.get(page)

    def resolve_tab(self, tab: Any) -> _StubPage:
        tabs = self.open_tabs()
        if not tabs:
            raise ValueError("No open tabs; call new_tab(url) first")
        if tab is None:
            if len(tabs) == 1:
                return tabs[0]
            raise ValueError(f"{len(tabs)} tabs open; specify tab=N.")
        target = int(str(tab).strip())
        for page, tid in self._ids.items():
            if tid == target and not page.is_closed():
                return page
        raise ValueError(f"tab={tab!r} not found.")

    # ── Page / navigation surface ─────────────────────────────────────
    async def new_page(self) -> _StubPage:
        page = _StubPage()
        self._pages.append(page)
        self._next_id += 1
        self._ids[page] = self._next_id
        return page

    async def navigate(self, url: str, *, page: _StubPage) -> BrowserInteractionResult:
        if page in self._pages_in_navigation:
            tid = self._ids.get(page)
            raise BrowserToolError(
                f"Navigation already in flight on tab={tid}. Use new_tab(url).",
                tool="goto",
            )
        self._pages_in_navigation.add(page)
        try:
            page.url = url
            return BrowserInteractionResult(
                navigation_response=None,
                download=None,
            )
        finally:
            self._pages_in_navigation.discard(page)

    async def active_view(self, page: _StubPage | None = None) -> ActiveView:
        if page is None:
            page = self.open_tabs()[-1]
        return ActiveView(frame=page, title="", url=page.url)


@pytest.fixture
def stub_browser(monkeypatch: pytest.MonkeyPatch) -> _StubBrowser:
    browser = _StubBrowser()

    async def _get_browser() -> _StubBrowser:
        return browser

    async def _no_screenshot() -> None:
        return None

    # Avoid the screenshot decorator trying to use a real browser.
    class _Stub:
        async def current_page(self) -> Any:
            return _StubPage()

    async def _events_get_browser() -> _Stub:
        return _Stub()

    async def _mock_build(response: Any, *, page: Any = None) -> PageView:
        return PageView(
            title="",
            url=page.url if page is not None else "",
            status_code=200,
            content="",
            viewport={"scroll_top": 0, "viewport_height": 0, "viewport_width": 0, "document_height": 0},
            truncated=False,
        )

    monkeypatch.setattr("tools.browser.navigation.browser_core.get_browser", _get_browser)
    monkeypatch.setattr("tools.browser.interactions.get_browser", _get_browser)
    monkeypatch.setattr("tools.browser.interactions._build_snapshot", _mock_build)
    monkeypatch.setattr("tools.browser.events.get_browser", _events_get_browser)
    return browser


@pytest.mark.unit
@pytest.mark.asyncio
async def test_goto_errors_when_no_tabs(stub_browser: _StubBrowser) -> None:
    """goto needs an existing tab — call new_tab first."""
    with pytest.raises(BrowserToolError, match="No open tabs"):
        await goto("https://example.com", tab="1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_goto_navigates_existing_tab(stub_browser: _StubBrowser) -> None:
    """goto re-points an existing tab in place."""
    await new_tab("https://example.com")
    await goto("https://other.com", tab="1")
    assert len(stub_browser.open_tabs()) == 1
    assert stub_browser.open_tabs()[0].url == "https://other.com"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_goto_with_tab_arg(stub_browser: _StubBrowser) -> None:
    """goto(url, tab='N') navigates that specific tab."""
    await new_tab("https://a.com")
    await new_tab("https://b.com")
    await goto("https://navigated.com", tab="1")
    tabs = stub_browser.open_tabs()
    assert tabs[0].url == "https://navigated.com"
    assert tabs[1].url == "https://b.com"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_goto_unknown_tab_errors(stub_browser: _StubBrowser) -> None:
    await new_tab("https://a.com")
    with pytest.raises(BrowserToolError, match="tab='99' not found"):
        await goto("https://c.com", tab="99")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_new_tab_opens_new(stub_browser: _StubBrowser) -> None:
    await new_tab("https://a.com")
    out = await new_tab("https://b.com")
    assert len(stub_browser.open_tabs()) == 2
    assert "tab=2" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_tab_removes_tab(stub_browser: _StubBrowser) -> None:
    await new_tab("https://a.com")
    await new_tab("https://b.com")
    output = await close_tab(tab="1")
    assert output == "Closed tab=1."
    assert len(stub_browser.open_tabs()) == 1
    assert stub_browser.open_tabs()[0].url == "https://b.com"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_tab_id_not_reused(stub_browser: _StubBrowser) -> None:
    """After closing a tab, new tabs get fresh IDs — closed ID is not reused."""
    await new_tab("https://a.com")  # tab 1
    await new_tab("https://b.com")  # tab 2
    await close_tab(tab="1")
    output = await new_tab("https://c.com")  # should be tab 3, not tab 1
    assert "tab=3" in output


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_tab_errors_when_unknown(stub_browser: _StubBrowser) -> None:
    await new_tab("https://a.com")
    with pytest.raises(BrowserToolError, match="not found"):
        await close_tab(tab="42")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_goto_on_different_tabs_both_succeed(
    stub_browser: _StubBrowser,
) -> None:
    """Concurrent goto on different tabs do not race — each lands correctly.

    This is the user-facing capability the multi-tab redesign was for:
    the agent can drive multiple tabs in one batch without them
    clobbering each other.
    """
    await new_tab("https://a.com")  # tab=1
    await new_tab("https://b.com")  # tab=2

    a_out, b_out = await asyncio.gather(
        goto("https://navigated-a.com", tab="1"),
        goto("https://navigated-b.com", tab="2"),
    )

    tabs = stub_browser.open_tabs()
    assert tabs[0].url == "https://navigated-a.com"
    assert tabs[1].url == "https://navigated-b.com"
    # Each result's header carries its own tab ID — no cross-contamination.
    assert "tab=1" in a_out
    assert "tab=2" in b_out
    assert "navigated-a.com" in a_out
    assert "navigated-b.com" in b_out
