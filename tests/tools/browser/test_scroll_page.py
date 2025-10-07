from __future__ import annotations

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import scroll_page


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/start"
        self._title = "Start"

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return "body text"

    async def query_selector_all(self, selector: str) -> list[object]:
        return []

    async def evaluate(self, js: str) -> object:
        # Return a reasonable fixed scroll state for tests
        return {"scroll_top": 0, "viewport_height": 600, "document_height": 2000}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_delegates(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = FakePage()
    patch_interactions_browser(page)

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        # simple assertion to ensure args are passed
        assert page_arg is page
        assert direction in {"down", "up", "page_down", "page_up", "top", "bottom"}

    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)

    result = await scroll_page("down")
    # Expect a dict with 'snapshot' (PageSnapshot) and 'scroll' telemetry
    assert isinstance(result, dict)
    assert "snapshot" in result and "scroll" in result
    snap: PageSnapshot = result["snapshot"]
    assert isinstance(snap, PageSnapshot)
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_invalid_direction() -> None:
    with pytest.raises(BrowserToolError):
        await scroll_page("")
