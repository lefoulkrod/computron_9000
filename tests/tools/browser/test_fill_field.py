"""Unit tests for the fill_field browser interaction tool."""

from __future__ import annotations

import pytest

try:  # pragma: no cover - fallback for environments without Playwright
    from playwright.async_api import Error as PlaywrightError
except ModuleNotFoundError:  # pragma: no cover - testing fallback
    class PlaywrightError(Exception):
        """Fallback Playwright error stub used when Playwright is unavailable."""


from tools.browser import BrowserToolError
from tools.browser.interactions import fill_field


async def _passthrough_human_click(page: object, locator: FakeLocator) -> None:
    await locator.click()


async def _passthrough_human_type(page: object, locator: FakeLocator, text: str, *, clear_existing: bool = True) -> None:
    if clear_existing:
        await locator.fill("")
    await locator.type(text)


class FakeElementHandle:
    """Minimal element handle supporting tag/type inspection."""

    def __init__(self, tag: str, input_type: str | None = None) -> None:
        self._tag = tag
        self._input_type = input_type or "text"

    async def evaluate(self, script: str):  # noqa: D401 - emulate Playwright interface
        if "tagName" in script:
            return self._tag
        raise PlaywrightError("Unsupported evaluation in fake handle")

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        if name == "type":
            return self._input_type
        return None


class FakeLocator:
    """Playwright Locator stub used by tests."""

    def __init__(
        self,
        page: "FakePage",
        *,
        tag: str = "input",
        input_type: str | None = None,
        exists: bool = True,
    ) -> None:
        self._page = page
        self._tag = tag
        self._input_type = input_type or "text"
        self._value = ""
        self._exists = exists
        self.first = self

    async def count(self) -> int:  # noqa: D401 - mimic Playwright
        return 1 if self._exists else 0

    async def fill(self, text: str) -> None:  # noqa: D401
        if not self._exists:
            raise PlaywrightError("element does not exist")
        if self._tag not in {"input", "textarea"}:
            raise PlaywrightError("fill not supported for this element")
        if self._tag == "input" and self._input_type in {"checkbox", "radio", "file"}:
            raise PlaywrightError(f"unsupported input type: {self._input_type}")
        self._value = text
        self._page.record_fill(self._value)

    async def select_option(self, value: str) -> None:  # noqa: D401
        if not self._exists:
            raise PlaywrightError("element does not exist")
        if self._tag != "select":
            raise PlaywrightError("select_option only valid for select elements")
        self._value = value
        self._page.record_fill(self._value)

    async def element_handle(self) -> FakeElementHandle | None:  # noqa: D401
        if not self._exists:
            return None
        return FakeElementHandle(self._tag, self._input_type)

    async def click(self) -> None:  # noqa: D401
        if not self._exists:
            raise PlaywrightError("element does not exist")

    async def type(self, text: str) -> None:  # noqa: D401
        if not self._exists:
            raise PlaywrightError("element does not exist")
        self._value = text
        self._page.record_fill(self._value)


class FakePage:
    """Minimal Playwright page stub for snapshot creation."""

    def __init__(self) -> None:
        self._title = "Initial"
        self._body_text = "Before fill"
        self.url = "https://example.test/form"
        self._css_locators: dict[str, FakeLocator] = {}
        self._text_locators: dict[str, FakeLocator] = {}
        self._anchors: list[object] = []
        self._forms: list[object] = []

    async def title(self) -> str:  # noqa: D401
        return self._title

    async def inner_text(self, selector: str) -> str:  # noqa: D401
        if selector == "body":
            return self._body_text
        raise PlaywrightError("Unsupported selector in fake page")

    async def query_selector_all(self, selector: str) -> list[object]:  # noqa: D401
        if selector == "a":
            return self._anchors
        if selector == "form":
            return self._forms
        return []

    def locator(self, selector: str) -> FakeLocator:  # noqa: D401
        return self._css_locators.get(selector, FakeLocator(self, tag="div", exists=False))

    def get_by_text(self, value: str, exact: bool = True) -> FakeLocator:  # noqa: D401
        return self._text_locators.get(value, FakeLocator(self, tag="div", exists=False))

    def record_fill(self, value: str) -> None:
        self._body_text = f"Filled value: {value}"

    def add_css_input(self, selector: str, *, tag: str = "input", input_type: str | None = None) -> None:
        self._css_locators[selector] = FakeLocator(self, tag=tag, input_type=input_type, exists=True)

    def add_text_input(self, text: str, *, tag: str = "input", input_type: str | None = None) -> None:
        self._text_locators[text] = FakeLocator(self, tag=tag, input_type=input_type, exists=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_by_css(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Types into an input located via CSS selector and returns updated snapshot."""
    page = FakePage()
    page.add_css_input(".search-box")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    snapshot = await fill_field(".search-box", "chips")
    assert "Filled value: chips" in snapshot.snippet
    assert snapshot.url.endswith("/form")
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_by_visible_text(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Falls back to exact visible text to locate the input field."""
    page = FakePage()
    page.add_text_input("Email")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    snapshot = await fill_field("Email", "user@example.com")
    assert "user@example.com" in snapshot.snippet
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_rejects_checkbox(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Rejects unsupported input types such as checkbox."""
    page = FakePage()
    page.add_css_input("#agree", input_type="checkbox")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("#agree", True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_requires_non_empty_selector(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Rejects whitespace-only selectors."""
    page = FakePage()
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("   ", "value")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_select_element(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Raising error for select elements which are no longer supported."""
    page = FakePage()
    page.add_css_input("#country", tag="select")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("#country", "us")
