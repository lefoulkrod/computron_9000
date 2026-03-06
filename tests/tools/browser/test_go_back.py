from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import go_back
from tests.tools.browser.support.playwright_stubs import StubPage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_go_back_navigates_backward(
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = StubPage(
        title="Start",
        body_text="Start body",
        url="https://example.test/start",
    )
    page._apply_navigation(
        url="https://example.test/next",
        title="Next",
        body="Next body",
    )
    patch_interactions_browser(page)

    result = await go_back()
    assert isinstance(result, str)
    assert "page_changed: yes" in result
    assert "browser-navigation" in result
    assert "https://example.test/start" in result
    assert "Start body" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_go_back_requires_history(patch_interactions_browser) -> None:
    page = StubPage(
        title="Only",
        body_text="Body",
        url="https://example.test/only",
    )
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await go_back()
