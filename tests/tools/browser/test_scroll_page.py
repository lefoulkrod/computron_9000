from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import InteractionResult, scroll_page
from tests.tools.browser.support.playwright_stubs import StubPage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_delegates(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = StubPage(
        title="Start",
        body_text="body text",
        url="https://example.test/start",
    )
    page.set_scroll_state(scroll_top=0, viewport_height=600, document_height=2000)
    patch_interactions_browser(page)

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        # simple assertion to ensure args are passed
        assert page_arg is page
        assert direction in {"down", "up", "page_down", "page_up", "top", "bottom"}

    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)

    result = await scroll_page("down")
    assert isinstance(result, InteractionResult)
    assert result.page_changed is False
    assert result.reason == "no-change"
    assert result.snapshot is None
    scroll = result.extras.get("scroll")
    assert isinstance(scroll, dict)
    assert scroll["scroll_top"] == 0
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_invalid_direction() -> None:
    with pytest.raises(BrowserToolError):
        await scroll_page("")
