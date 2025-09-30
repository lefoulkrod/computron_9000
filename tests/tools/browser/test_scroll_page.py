from __future__ import annotations

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import scroll_page


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/start"
        self._title = "Start"

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return "body text"

    async def query_selector_all(self, selector: str) -> list[object]:
        return []


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    async def current_page(self) -> FakePage:
        return self._page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage()
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return fake_browser

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        # simple assertion to ensure args are passed
        assert page_arg is page
        assert direction in {"down", "up", "page_down", "page_up", "top", "bottom"}

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)

    called = {"count": 0}

    async def fake_wait(page: object, *, expect_navigation: bool, waits: object) -> None:
        called["count"] += 1

    monkeypatch.setattr("tools.browser.interactions._wait_for_page_settle", fake_wait)

    snap: PageSnapshot = await scroll_page("down")
    assert isinstance(snap, PageSnapshot)
    assert called["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_invalid_direction() -> None:
    with pytest.raises(BrowserToolError):
        await scroll_page("")
