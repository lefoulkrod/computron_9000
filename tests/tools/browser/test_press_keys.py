from __future__ import annotations

import pytest

from typing import Any, cast

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import press_keys
from tests.tools.browser.support.playwright_stubs import StubPage


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(f"press:{key}")

    async def down(self, key: str) -> None:
        self.pressed.append(f"down:{key}")

    async def up(self, key: str) -> None:
        self.pressed.append(f"up:{key}")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_keys_success(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    keyboard = FakeKeyboard()
    page = StubPage(
        title="Initial",
        body_text="Before press",
        url="https://example.test/start",
    )
    page.keyboard = keyboard  # type: ignore[attr-defined]
    patch_interactions_browser(page)

    async def fake_human_press_keys(page: object, keys: list[str]) -> None:
        # simulate pressing keys by delegating to page.keyboard
        stub_page = cast(StubPage, page)
        for k in keys:
            await cast(Any, stub_page.keyboard).press(k)

    monkeypatch.setattr("tools.browser.interactions.human_press_keys", fake_human_press_keys)

    snap: PageSnapshot = await press_keys(["Enter"])  # should return a snapshot
    assert isinstance(snap, PageSnapshot)
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_keys_invalid_input() -> None:
    with pytest.raises(BrowserToolError):
        await press_keys([])
