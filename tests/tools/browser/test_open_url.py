import pytest

from tools.browser import BrowserToolError
from tools.browser.page import open_url
from tests.tools.browser.support.playwright_stubs import StubBrowser, StubPage


class _NoSnapshotPage:
    """Page stub with no screenshot capability; causes the events decorator to exit early."""


class _NoSnapshotBrowser:
    async def current_page(self) -> _NoSnapshotPage:
        return _NoSnapshotPage()


async def _no_snapshot_get_browser() -> _NoSnapshotBrowser:
    return _NoSnapshotBrowser()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_returns_page_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url returns a formatted string with title, url, and content."""

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
    monkeypatch.setattr("tools.browser.events.get_browser", _no_snapshot_get_browser)

    result = await open_url("https://example.com")

    assert isinstance(result, str)
    assert "Example Title" in result
    assert "https://example.com/final" in result
    assert "Hello from example" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_viewport_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url populates viewport metadata in the output."""

    page = StubPage(title="T", body_text="Body text")
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.events.get_browser", _no_snapshot_get_browser)

    result = await open_url("https://example.com")

    assert isinstance(result, str)
    assert "Viewport:" in result


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
