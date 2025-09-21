import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.page import current_page


class FakePage:
    def __init__(self, title: str, body: str, url: str) -> None:
        self._title = title
        self._body = body
        self.url = url
        self._closed = False

    async def title(self) -> str:  # noqa: D401 - simple stub
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return self._body

    async def query_selector_all(self, selector: str):  # noqa: D401 - stub
        # No links/forms for this simplified test
        return []

    def is_closed(self) -> bool:  # noqa: D401 - stub
        return self._closed


class FakeBrowser:
    def __init__(self, pages):  # noqa: D401 - simple stub
        self._pages = pages

    async def pages(self):  # noqa: D401 - mimic Browser.pages
        return list(self._pages)

    async def current_page(self):  # noqa: D401 - mimic new Browser.current_page semantics
        for p in reversed(self._pages):
            if not p.is_closed():
                return p
        raise RuntimeError("No open pages available in browser context")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_success(monkeypatch):
    """current_page returns snapshot of most recent open page."""
    p1 = FakePage("Old", "First body", "https://old")
    p2 = FakePage("Active", "Second body text", "https://active")
    fake_browser = FakeBrowser([p1, p2])

    async def fake_get_browser():  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    snap: PageSnapshot = await current_page()
    assert snap.title == "Active"
    assert snap.url == "https://active"
    assert snap.snippet.startswith("Second body")
    assert snap.status_code is None  # no navigation response
    assert snap.links == []
    assert snap.forms == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_no_pages(monkeypatch):
    """current_page raises when there are no pages."""
    fake_browser = FakeBrowser([])

    async def fake_get_browser():  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await current_page()
