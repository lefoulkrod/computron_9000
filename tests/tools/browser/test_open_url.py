import pytest

from tools.browser import BrowserToolError
from tools.browser.core.page_view import PageView
from tools.browser.page import open_url
from tests.tools.browser.support.playwright_stubs import StubBrowser, StubPage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_returns_page_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url returns a PageView with title, url, status_code, and content."""

    page = StubPage(
        title="Example Title",
        body_text="Hello from example",
        final_url="https://example.com/final",
        status=200,
    )
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    result = await open_url("https://example.com")

    assert isinstance(result, PageView)
    assert result.title == "Example Title"
    assert result.url == "https://example.com/final"
    assert result.status_code == 200
    assert "Hello from example" in result.content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_viewport_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url populates viewport metadata from the page."""

    page = StubPage(title="T", body_text="Body text")
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    result = await open_url("https://example.com")

    assert isinstance(result, PageView)
    assert "viewport_height" in result.viewport
    assert "document_height" in result.viewport


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Errors are wrapped in BrowserToolError."""

    class BoomPage(StubPage):
        async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    page = BoomPage(title="T", body_text="")
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await open_url("https://example.com")
