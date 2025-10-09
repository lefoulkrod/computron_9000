from __future__ import annotations

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import drag


async def _human_drag_probe(
    page: "FakePage",
    source_locator: "FakeLocator",
    *,
    target_locator: "FakeLocator | None" = None,
    offset: tuple[float, float] | None = None,
) -> None:
    page.drag_calls.append(
        {
            "source": source_locator,
            "target": target_locator,
            "offset": offset,
        }
    )


class FakeLocator:
    def __init__(self, page: "FakePage", key: str, present: bool = True) -> None:
        self._page = page
        self.key = key
        self._present = present

    async def count(self) -> int:
        return 1 if self._present else 0

    @property
    def first(self) -> "FakeLocator":
        return self


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/drag"
        self._title = "Drag Playground"
        self._body_text = "Welcome to the drag playground."
        self._text_locators: dict[str, FakeLocator] = {}
        self._css_locators: dict[str, FakeLocator] = {}
        self.drag_calls: list[dict[str, object]] = []

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return self._body_text

    async def query_selector_all(self, selector: str) -> list[object]:
        return []

    def get_by_text(self, text: str, exact: bool = True) -> FakeLocator:
        return self._text_locators.get(text, FakeLocator(self, f"text={text}", present=False))

    def locator(self, selector: str) -> FakeLocator:
        return self._css_locators.get(selector, FakeLocator(self, selector, present=False))

    def add_text(self, text: str) -> FakeLocator:
        loc = FakeLocator(self, f"text={text}", present=True)
        self._text_locators[text] = loc
        return loc

    def add_selector(self, selector: str) -> FakeLocator:
        loc = FakeLocator(self, selector, present=True)
        self._css_locators[selector] = loc
        return loc


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_with_target_selector(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = FakePage()
    source_locator = page.add_selector("#handle")
    target_locator = page.add_selector(".drop-zone")

    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_drag", _human_drag_probe)

    snapshot = await drag("#handle", target=".drop-zone")
    assert isinstance(snapshot, PageSnapshot)
    assert page.drag_calls == [
        {"source": source_locator, "target": target_locator, "offset": None}
    ]
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_with_offset(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = FakePage()
    source_locator = page.add_text("Drag me")

    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_drag", _human_drag_probe)

    snapshot = await drag("Drag me", offset=(25, -10))
    assert isinstance(snapshot, PageSnapshot)
    assert page.drag_calls == [
        {"source": source_locator, "target": None, "offset": (25.0, -10.0)}
    ]
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_requires_destination(
    patch_interactions_browser,
) -> None:
    page = FakePage()
    page.add_selector("#handle")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("#handle")

    with pytest.raises(BrowserToolError):
        await drag("#handle", target=".missing", offset=(5, 5))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_target_not_found(
    patch_interactions_browser,
) -> None:
    page = FakePage()
    page.add_selector("#handle")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("#handle", target=".missing")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_invalid_offset_type(
    patch_interactions_browser,
) -> None:
    page = FakePage()
    page.add_text("Drag me")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("Drag me", offset=("bad", 5))  # type: ignore[arg-type]
