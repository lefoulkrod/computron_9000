import pytest

from tools.browser import BrowserToolError
from tools.browser.search import TextExtractionResult, extract_text


class FakeLocator:
    def __init__(self, page: "FakePage", texts: list[str] | None = None) -> None:  # noqa: D401
        self._page = page
        self._texts = texts or []

    async def count(self) -> int:  # noqa: D401 - stub
        return len(self._texts)

    def nth(self, idx: int) -> "FakeElement":  # noqa: D401 - stub
        return FakeElement(self._texts[idx])

    async def inner_text(self) -> str:  # noqa: D401 - for text fallback first
        if not self._texts:
            return ""
        return self._texts[0]

    @property
    def first(self) -> "FakeLocator":  # noqa: D401
        return self

    async def wait_for(self, timeout: int) -> None:  # noqa: D401 - stub always success
        return None


class FakeElement:
    def __init__(self, text: str) -> None:  # noqa: D401
        self._text = text

    async def inner_text(self) -> str:  # noqa: D401 - stub
        return self._text


class FakePage:
    def __init__(self) -> None:  # noqa: D401
        self.url = "https://example.test/page"
        self._css: dict[str, list[str]] = {}
        self._text_map: dict[str, list[str]] = {}

    def locator(self, selector: str) -> FakeLocator:  # noqa: D401
        return FakeLocator(self, self._css.get(selector, []))

    def get_by_text(self, value: str, exact: bool = False) -> FakeLocator:  # noqa: D401
        # Return a locator with a single entry if key present.
        texts = self._text_map.get(value, [])
        return FakeLocator(self, texts)

    def add_css(self, selector: str, texts: list[str]) -> None:  # noqa: D401
        self._css[selector] = texts

    def add_text(self, value: str, text: str) -> None:  # noqa: D401
        self._text_map[value] = [text]


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:  # noqa: D401
        self._page = page

    async def current_page(self) -> FakePage:  # noqa: D401
        return self._page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_text_by_css(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extracts multiple elements via CSS selector."""
    page = FakePage()
    page.add_css("div.item", ["First Item", "Second Item"])
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401
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
    page = FakePage()
    page.add_text("Business Hours", "Business Hours: 9-5")
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401
        return fake_browser

    monkeypatch.setattr("tools.browser.search.get_browser", fake_get_browser)

    results = await extract_text("Business Hours")
    assert len(results) == 1
    assert results[0].selector.startswith("text=Business Hours")
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
    page = FakePage()
    long_text = "A" * 500
    page.add_css("p.long", [long_text])
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401
        return fake_browser

    monkeypatch.setattr("tools.browser.search.get_browser", fake_get_browser)

    results = await extract_text("p.long", limit=50)
    assert len(results) == 1
    assert len(results[0].text) == 50
