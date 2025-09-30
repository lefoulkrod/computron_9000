from __future__ import annotations

import pytest

from typing import Any, cast

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import press_keys


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(f"press:{key}")

    async def down(self, key: str) -> None:
        self.pressed.append(f"down:{key}")

    async def up(self, key: str) -> None:
        self.pressed.append(f"up:{key}")


class FakePage:
    def __init__(self, keyboard: FakeKeyboard):
        self._title = "Initial"
        self._body_text = "Before press"
        self.url = "https://example.test/start"
        self.keyboard = keyboard

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return self._body_text

    async def query_selector_all(self, selector: str) -> list[object]:
        if selector == "a":
            return []
        if selector == "form":
            return []
        return []


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    async def current_page(self) -> FakePage:
        return self._page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_keys_success(monkeypatch: pytest.MonkeyPatch) -> None:
    keyboard = FakeKeyboard()
    page = FakePage(keyboard)
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return fake_browser

    async def fake_human_press_keys(page: object, keys: list[str]) -> None:
        # simulate pressing keys by delegating to page.keyboard
        from typing import Any
        for k in keys:
            await cast(Any, page).keyboard.press(k)
        

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.interactions.human_press_keys", fake_human_press_keys)

    called = {"count": 0}

    async def fake_wait(page: object, *, expect_navigation: bool, waits: object) -> None:
        called["count"] += 1

    monkeypatch.setattr("tools.browser.interactions._wait_for_page_settle", fake_wait)

    snap: PageSnapshot = await press_keys(["Enter"])  # should return a snapshot
    assert isinstance(snap, PageSnapshot)
    assert called["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_keys_invalid_input() -> None:
    with pytest.raises(BrowserToolError):
        await press_keys([])
