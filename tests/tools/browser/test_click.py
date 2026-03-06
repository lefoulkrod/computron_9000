from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
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

    result = await click("Continue")
    assert isinstance(result, str)
    assert "page_changed: yes" in result
    assert "browser-navigation" in result
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
    assert "page_changed: yes" in result
    assert "browser-navigation" in result
    assert "/cta" in result
    assert "After Click" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_role_name_suggests_full_name_on_partial_match(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Surfaces the full accessible name when visible text is only a prefix."""
    page = StubPage(
        title="Cart",
        body_text="Shopping Cart",
        url="https://example.test/cart",
    )
    page.add_role_locator(
        "button",
        name="Proceed to checkout Check out Amazon Cart",
        tag="input",
        input_type="submit",
        text_value="Proceed to checkout",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    with pytest.raises(BrowserToolError, match="No exact match"):
        await click("button:Proceed to checkout")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_role_name_works_with_full_accessible_name(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Clicking with the full accessible name succeeds on the first try."""
    page = StubPage(
        title="Cart",
        body_text="Shopping Cart",
        url="https://example.test/cart",
    )
    page.add_role_locator(
        "button",
        name="Proceed to checkout Check out Amazon Cart",
        tag="input",
        input_type="submit",
        navigates_to="https://example.test/checkout",
        navigation_title="Checkout",
        navigation_body="Checkout page",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    result = await click("button:Proceed to checkout Check out Amazon Cart")
    assert isinstance(result, str)
    assert "page_changed: yes" in result
    assert "https://example.test/checkout" in result


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
