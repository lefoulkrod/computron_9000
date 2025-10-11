import pytest

from tools.browser import BrowserToolError
from tools.browser.search import TextExtractionResult, extract_text
from tests.tools.browser.support.playwright_stubs import StubBrowser, StubPage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_text_by_css(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extracts multiple elements via CSS selector."""
    page = StubPage(url="https://example.test/page")
    page.add_css_locator("div.item", tag="div", texts=["First Item", "Second Item"])
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.search.get_browser", fake_get_browser)

    results = await extract_text("div.item")
    assert len(results) == 2
    assert all(isinstance(r, TextExtractionResult) for r in results)
    assert results[0].selector.startswith("div.item")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_text_fallback_visible_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to visible text when CSS selector yields nothing."""
    page = StubPage(url="https://example.test/page")
    page.add_text_locator("Business Hours", tag="div", text_value="Business Hours: 9-5")
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.search.get_browser", fake_get_browser)

    results = await extract_text("Business Hours")
    assert len(results) == 1
    selector = results[0].selector
    assert selector.startswith("text=Business Hours") or selector.startswith("body > div")
    assert "9-5" in results[0].text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_text_empty_target() -> None:
    """Raises BrowserToolError for empty/whitespace target."""
    with pytest.raises(BrowserToolError):
        await extract_text("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_text_limit_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Truncates text to provided character limit."""
    page = StubPage(url="https://example.test/page")
    long_text = "A" * 500
    page.add_css_locator("p.long", tag="p", texts=[long_text])
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.search.get_browser", fake_get_browser)

    results = await extract_text("p.long", limit=50)
    assert len(results) == 1
    assert len(results[0].text) == 50
