from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import click
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _human_click_passthrough(page: object, locator: StubLocator) -> None:
    await locator.click()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_by_ref(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Clicking by ref number performs navigation and returns a snapshot."""

    page = StubPage(
        title="Initial",
        body_text="Before click",
        url="https://example.test/start",
    )
    page.add_ref_locator(
        1,
        navigates_to="https://example.test/after",
        navigation_title="After Click",
        navigation_body="Arrived after navigation",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    result = await click("1")
    assert isinstance(result, str)
    assert "[Page:" in result
    assert "https://example.test/after" in result
    assert "After Click" in result
    assert "Arrived" in result
    assert settle_tracker["count"] == 1


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

    result = await click(".cta")
    assert "[Page:" in result
    assert "/cta" in result
    assert "After Click" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_ref_not_found(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Returns error when ref number doesn't exist on the page."""
    page = StubPage(
        title="Cart",
        body_text="Shopping Cart",
        url="https://example.test/cart",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    result = await click("99")
    assert "Ref 99 not found" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_not_found(monkeypatch: pytest.MonkeyPatch, patch_interactions_browser) -> None:
    """Returns error string when element can't be located."""

    page = StubPage(
        title="Initial",
        body_text="Before click",
        url="https://example.test/start",
    )
    # Use shared patch_interactions_browser fixture to patch get_browser
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    result = await click("Does Not Exist")
    assert "No element found" in result
