from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.core.page_view import PageView
from tools.browser.interactions import InteractionResult, click
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
    assert isinstance(result, InteractionResult)
    assert result.page_changed is True
    assert result.reason == "browser-navigation"
    snap: PageView = result.page_view
    assert snap.url == "https://example.test/after"
    assert snap.title == "After Click"
    assert "Arrived" in snap.content
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

    result = await click(".cta")
    assert result.page_changed is True
    assert result.reason == "browser-navigation"
    snap = result.page_view
    assert snap.url.endswith("/cta")
    assert snap.title == "After Click"
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [True]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_role_name_suggests_full_name_on_partial_match(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Surfaces the full accessible name when visible text is only a prefix.

    Amazon's checkout button has visible text "Proceed to checkout" but the
    Playwright accessible name is "Proceed to checkout Check out Amazon Cart"
    (from hidden text in the aria-labelledby target).  The exact match fails,
    so _resolve_locator raises an error suggesting the full name instead of
    silently clicking a fuzzy match (which could target the wrong element).
    """
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

    # Agent uses the visible text — should get a helpful error, not a silent click
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

    # Agent retries with the full name from the error suggestion
    result = await click("button:Proceed to checkout Check out Amazon Cart")
    assert isinstance(result, InteractionResult)
    assert result.page_changed is True
    assert result.page_view.url == "https://example.test/checkout"


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
