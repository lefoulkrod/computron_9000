import pytest

from typing import Any

from tools.browser.core.browser import Browser


class FakePage:
    def __init__(self, closed: bool = False) -> None:
        self._closed = closed

    def is_closed(self) -> bool:
        return self._closed

    async def set_viewport_size(self, size: dict[str, int]) -> None:  # noqa: D401 - stub
        return None


class FakeContext:
    def __init__(self, pages: list[FakePage] | None = None) -> None:
        self.pages = pages or []

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_returns_last_open_page() -> None:
    """current_page returns most recently opened non-closed page."""
    pages = [FakePage(closed=True), FakePage(closed=False)]
    ctx = FakeContext(pages)
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    page = await browser.current_page()
    assert page is pages[-1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_creates_when_none() -> None:
    """current_page creates a new page if none exist or all closed."""
    ctx = FakeContext([])
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    page = await browser.current_page()
    assert page in ctx.pages
    assert len(ctx.pages) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_skips_closed_pages() -> None:
    """current_page skips closed pages when selecting current."""
    ctx = FakeContext([FakePage(closed=True), FakePage(closed=True)])
    browser = Browser(context=ctx, extra_headers={})  # type: ignore[arg-type]

    page = await browser.current_page()
    assert page in ctx.pages
    assert not page.is_closed()
