from __future__ import annotations

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import click
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _human_click_passthrough(page: object, locator: StubLocator) -> None:
    await locator.click()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_by_text(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Clicking by visible text performs navigation and returns a snapshot."""

    page = StubPage(
        title="Initial",
        body_text="Before click",
        url="https://example.test/start",
    )
    page.add_text_locator(
        "Continue",
        navigates_to="https://example.test/after",
        navigation_title="After Click",
        navigation_body="Arrived after navigation",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    snap: PageSnapshot = await click("Continue")
    assert snap.url == "https://example.test/after"
    assert snap.title == "After Click"
    assert "Arrived" in snap.snippet
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [True]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_by_css_selector(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Falls back to CSS selector when no text match exists."""

    page = StubPage(
        title="Initial",
        body_text="Before click",
        url="https://example.test/start",
    )
    page.add_css_locator(
        ".cta",
        navigates_to="https://example.test/cta",
        navigation_title="After Click",
        navigation_body="Arrived after navigation",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    snap = await click(".cta")
    assert snap.url.endswith("/cta")
    assert snap.title == "After Click"
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [True]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_not_found(monkeypatch: pytest.MonkeyPatch, patch_interactions_browser) -> None:
    """Raises BrowserToolError when element can't be located."""

    page = StubPage(
        title="Initial",
        body_text="Before click",
        url="https://example.test/start",
    )
    # Use shared patch_interactions_browser fixture to patch get_browser
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    with pytest.raises(BrowserToolError):
        await click("Does Not Exist")
