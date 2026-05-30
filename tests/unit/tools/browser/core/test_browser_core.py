import pytest

from typing import Any

from tools.browser.core.browser import Browser
from tools.browser.core.exceptions import BrowserToolError


class FakePage:
    def __init__(self, closed: bool = False) -> None:
        self._closed = closed
        self.url = ""

    def is_closed(self) -> bool:
        return self._closed

    def on(self, event: str, callback: Any) -> None:
        pass

    async def set_viewport_size(self, size: dict[str, int]) -> None:  # noqa: D401 - stub
        return None


class FakeContext:
    def __init__(self, pages: list[FakePage] | None = None) -> None:
        self.pages = pages or []

    def on(self, event: str, callback: Any) -> None:
        pass

    def remove_listener(self, event: str, callback: Any) -> None:
        pass

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_tabs_filters_closed() -> None:
    """open_tabs returns only non-closed pages."""
    pages = [FakePage(closed=False), FakePage(closed=True), FakePage(closed=False)]
    ctx = FakeContext(pages)
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    tabs = browser.open_tabs()
    assert tabs == [pages[0], pages[2]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_tabs_empty() -> None:
    """open_tabs returns an empty list when no pages exist."""
    ctx = FakeContext([])
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    assert browser.open_tabs() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_new_page_assigns_monotonic_id() -> None:
    """Each new_page gets a fresh, monotonically-increasing tab ID."""
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    p1 = await browser.new_page()
    p2 = await browser.new_page()
    p3 = await browser.new_page()

    assert browser.tab_id_of(p1) == 1
    assert browser.tab_id_of(p2) == 2
    assert browser.tab_id_of(p3) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tab_id_not_reused_after_close() -> None:
    """Closing a tab does not free its ID for reuse."""
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    p1 = await browser.new_page()
    p2 = await browser.new_page()
    # Simulate closing p1 — Browser's _on_close handler is wired to the
    # page's 'close' event, but FakePage doesn't dispatch it, so prune
    # by hand to mirror what the listener does.
    p1._closed = True
    browser._tab_id_of.pop(p1, None)

    p3 = await browser.new_page()
    # p3 gets ID 3, NOT 1 — the closed ID stays gone.
    assert browser.tab_id_of(p3) == 3
    assert browser.tab_id_of(p2) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_tab_by_id() -> None:
    """resolve_tab looks up pages by their stable ID."""
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    p1 = await browser.new_page()
    p2 = await browser.new_page()

    assert browser.resolve_tab("1") is p1
    assert browser.resolve_tab(2) is p2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_tab_errors_when_id_unknown() -> None:
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    await browser.new_page()

    with pytest.raises(ValueError, match="not found"):
        browser.resolve_tab("99")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_tab_id_missing_reports_not_found_even_when_no_tabs() -> None:
    """A specific tab id that doesn't exist should say 'not found', not
    'no open tabs' — the caller knew which tab they wanted, the right
    error is about that specific tab.
    """
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not found"):
        browser.resolve_tab("3")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_goto_on_same_tab_errors() -> None:
    """A second navigate while one is in flight on the same tab errors loudly."""
    ctx = FakeContext()
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    page = await browser.new_page()
    browser._pages_in_navigation.add(page)  # simulate in-flight nav

    with pytest.raises(BrowserToolError, match="in flight"):
        await browser.navigate("https://example.com", page=page)
