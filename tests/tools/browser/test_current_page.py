import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.page import current_page
from tests.tools.browser.support.playwright_stubs import StubBrowserWithPages, StubPage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_success(monkeypatch):
    """current_page returns snapshot of most recent open page."""
    p1 = StubPage(title="Old", body_text="First body", url="https://old")
    p2 = StubPage(title="Active", body_text="Second body text", url="https://active")
    fake_browser = StubBrowserWithPages([p1, p2])

    async def fake_get_browser():
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    snap: PageSnapshot = await current_page()
    assert snap.title == "Active"
    assert snap.url == "https://active"
    assert snap.snippet.startswith("Second body")
    assert snap.status_code is None  # no navigation response
    assert snap.elements == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_page_no_pages(monkeypatch):
    """current_page raises when there are no pages."""
    fake_browser = StubBrowserWithPages([])

    async def fake_get_browser():
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await current_page()
