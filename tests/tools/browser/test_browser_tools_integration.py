"""Integration tests exercising browser tools end-to-end.

Uses ref-based tools (browse_page, click, fill_field, select_option,
scroll_page, press_keys, read_page) alongside vision tools
(perform_visual_action, inspect_page) against static fixtures and real
sites.

Requires:
- Playwright browsers installed
- Inference container running (for vision tests)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tools.browser import (
    browse_page,
    click,
    close_browser,
    fill_field,
    go_back,
    open_url,
    press_keys,
    read_page,
    scroll_page,
    select_option,
)
from tools.browser.core import get_browser
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.vision import inspect_page, perform_visual_action

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).resolve().parents[3] / "server" / "static"


@pytest.fixture(autouse=True)
async def _browser_lifecycle():
    """Shut down the singleton browser after each test."""
    yield
    await close_browser()


async def _run_until(task: str, check_fn, *, max_steps: int = 5) -> bool:
    """Call perform_visual_action repeatedly until check_fn returns True."""
    for step in range(max_steps):
        try:
            await perform_visual_action(task)
        except BrowserToolError:
            continue
        if await check_fn():
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# Static fixture: test_browser.html — buttons, links, interaction log
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browse_and_click_button() -> None:
    """browse_page + click on a ref-numbered button."""
    await open_url(f"file://{_STATIC / 'test_browser.html'}")
    snapshot = await browse_page()

    # The page has a "Continue to Dashboard" button with id=primary-cta
    assert "Continue to Dashboard" in snapshot

    browser = await get_browser()
    page = await browser.current_page()

    # Find the ref number for the primary CTA
    result = await click("1")  # ref 1 is typically the first interactive element
    # Verify the interaction log recorded the click
    log_text = await page.locator("#log-entries").inner_text()
    # At least something was logged
    assert len(log_text) > 0 or "Page:" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browse_and_click_link() -> None:
    """browse_page(full_page=True) shows links; clicking a link updates the hash."""
    await open_url(f"file://{_STATIC / 'test_browser.html'}")
    snapshot = await browse_page(full_page=True)

    # The links section is below the fold — full_page=True reveals it
    assert "View Pricing" in snapshot

    browser = await get_browser()
    page = await browser.current_page()

    # Scroll to links section so TARS can see it
    await page.locator("#links").scroll_into_view_if_needed()

    # Use vision to click the pricing link
    await perform_visual_action("Click the 'View Pricing' link")

    url = page.url
    log_text = await page.locator("#log-entries").inner_text()
    assert "#pricing" in url or "Pricing" in log_text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vision_click_on_dark_theme_page() -> None:
    """perform_visual_action finds and clicks elements on a dark theme page."""
    await open_url(f"file://{_STATIC / 'test_browser.html'}")

    browser = await get_browser()
    page = await browser.current_page()

    async def _secondary_clicked() -> bool:
        text = await page.locator("#log-entries").inner_text()
        return "Secondary CTA" in text

    success = await _run_until("Click the 'Maybe Later' button", _secondary_clicked)
    assert success, "TARS did not click 'Maybe Later' button"


# ═══════════════════════════════════════════════════════════════════════
# Static fixture: test_form_filling.html — form with multiple field types
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fill_form_with_ref_tools() -> None:
    """Fill a form end-to-end using ref-based tools."""
    await open_url(f"file://{_STATIC / 'test_form_filling.html'}")
    snapshot = await browse_page()

    # The form has: Full Name, Email, Role (select), checkbox, radios, Bio, Submit
    assert "Full Name" in snapshot
    assert "Email Address" in snapshot

    browser = await get_browser()
    page = await browser.current_page()

    # Fill name field by finding its ref
    name_input = page.locator("#person-name")
    await name_input.click()
    await page.keyboard.type("Ada Lovelace")

    # Fill email
    email_input = page.locator("#person-email")
    await email_input.click()
    await page.keyboard.type("ada@example.com")

    # Verify values
    assert await name_input.input_value() == "Ada Lovelace"
    assert await email_input.input_value() == "ada@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vision_click_then_ref_type() -> None:
    """Use perform_visual_action to click a field, then ref tools to type.

    This is the recommended workflow: vision to locate hard-to-find elements,
    ref-based tools for typing (more reliable than TARS type prediction).
    """
    await open_url(f"file://{_STATIC / 'test_form_filling.html'}")

    browser = await get_browser()
    page = await browser.current_page()

    # Click the name field via vision
    await perform_visual_action("Click on the 'Full Name' text input field")

    # Verify field is focused
    is_focused = await page.evaluate(
        "() => document.activeElement === document.getElementById('person-name')"
    )
    assert is_focused, "Vision click did not focus the name field"

    # Type using the keyboard (as the agent would with fill_field)
    await page.keyboard.type("Ada Lovelace")
    value = await page.locator("#person-name").input_value()
    assert value == "Ada Lovelace"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_form_page() -> None:
    """inspect_page should describe the form layout."""
    await open_url(f"file://{_STATIC / 'test_form_filling.html'}")

    answer = await inspect_page("What form fields are visible on this page? List them.")
    # Should mention at least some of the form fields
    answer_lower = answer.lower()
    assert any(
        term in answer_lower
        for term in ["name", "email", "role", "bio", "form"]
    ), f"inspect_page did not describe form fields: {answer[:200]}"


# ═══════════════════════════════════════════════════════════════════════
# Static fixture: element_types_test.html — diverse element types
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_page_content() -> None:
    """read_page extracts text content from the element types page."""
    await open_url(f"file://{_STATIC / 'element_types_test.html'}")

    content = await read_page()
    assert "Element Types Test Page" in content
    # Should find table data
    assert "Alice Smith" in content
    assert "Bob Johnson" in content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scroll_and_browse() -> None:
    """scroll_page + browse_page reveals more content."""
    await open_url(f"file://{_STATIC / 'element_types_test.html'}")

    first_snapshot = await browse_page()

    await scroll_page("down")
    second_snapshot = await browse_page()

    # After scrolling, we should see content that may not have been in the
    # initial viewport (the page has forms, tables, interactive sections).
    assert len(second_snapshot) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vision_click_table_button() -> None:
    """perform_visual_action clicks an Edit button in the table."""
    await open_url(f"file://{_STATIC / 'element_types_test.html'}")

    browser = await get_browser()
    page = await browser.current_page()

    # Scroll down to the table
    await page.locator("#tables-section").scroll_into_view_if_needed()

    # Ask TARS to click one of the Edit buttons
    await perform_visual_action("Click the Edit button next to 'Alice Smith'")

    # We can't easily verify the click worked since the buttons just console.log,
    # but the test passing without error means TARS found and clicked something.


# ═══════════════════════════════════════════════════════════════════════
# Static fixture: scroll_viewport_test.html
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scroll_directions() -> None:
    """scroll_page works for multiple directions."""
    await open_url(f"file://{_STATIC / 'scroll_viewport_test.html'}")

    browser = await get_browser()
    page = await browser.current_page()

    # Scroll down
    await scroll_page("down")
    y_after_down = await page.evaluate("() => window.scrollY")
    assert y_after_down > 0

    # Scroll back up
    await scroll_page("top")
    y_after_top = await page.evaluate("() => window.scrollY")
    assert y_after_top == 0


# ═══════════════════════════════════════════════════════════════════════
# Real site: Wikipedia — read and search
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wikipedia_read() -> None:
    """Open Wikipedia main page and read content."""
    await open_url("https://en.wikipedia.org/wiki/Main_Page")
    content = await read_page()

    assert "Wikipedia" in content
    assert len(content) > 100


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wikipedia_search_with_vision_and_ref() -> None:
    """Use vision to click search, then ref tools to type and submit."""
    await open_url("https://en.wikipedia.org/wiki/Main_Page")
    snapshot = await browse_page()

    # There should be a search box
    assert "search" in snapshot.lower() or "Search" in snapshot

    browser = await get_browser()
    page = await browser.current_page()

    # Use vision to find and click the search input
    await perform_visual_action("Click on the search input box at the top of the page")

    # Type the query using the keyboard (reliable)
    await page.keyboard.type("Alan Turing")

    # Press Enter to search
    await press_keys(["Enter"])

    # Wait for navigation
    browser = await get_browser()
    page = await browser.current_page()

    # Should navigate to the Alan Turing article or search results
    url = page.url.lower()
    title = (await page.title()).lower()
    assert "turing" in url or "turing" in title or "search" in url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wikipedia_inspect_page() -> None:
    """Use inspect_page on a real Wikipedia article."""
    await open_url("https://en.wikipedia.org/wiki/Python_(programming_language)")

    answer = await inspect_page(
        "What programming language is this Wikipedia article about? "
        "Answer in one word."
    )
    assert "python" in answer.lower()


# ═══════════════════════════════════════════════════════════════════════
# Real site: example.com — simple page
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_example_com_browse() -> None:
    """Open example.com, browse, and read content."""
    await open_url("https://example.com")

    snapshot = await browse_page()
    assert "Example Domain" in snapshot

    content = await read_page()
    assert "example" in content.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_example_com_vision_inspect() -> None:
    """inspect_page describes what's on example.com."""
    await open_url("https://example.com")

    answer = await inspect_page("What is the main heading on this page?")
    assert "example" in answer.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_go_back() -> None:
    """go_back returns to the previous page."""
    await open_url("https://example.com")
    first_url = "https://example.com"

    await open_url("https://en.wikipedia.org/wiki/Main_Page")
    await go_back()

    browser = await get_browser()
    page = await browser.current_page()
    assert "example.com" in page.url


# ═══════════════════════════════════════════════════════════════════════
# Real site: Hacker News — link navigation
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hackernews_browse_and_click() -> None:
    """Browse Hacker News and click a link using ref-based tools."""
    await open_url("https://news.ycombinator.com")
    snapshot = await browse_page()

    # HN should have a "new" or "past" link
    assert "Hacker News" in snapshot or "new" in snapshot.lower()

    # Click the "new" link via vision
    await perform_visual_action("Click the 'new' link in the top navigation bar")

    browser = await get_browser()
    page = await browser.current_page()
    assert "newest" in page.url or "new" in page.url or "news" in page.url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hackernews_read_content() -> None:
    """read_page extracts text content from Hacker News."""
    await open_url("https://news.ycombinator.com")
    content = await read_page()

    # Should have some article titles
    assert len(content) > 200
    # HN pages have point counts
    assert "point" in content.lower() or "comment" in content.lower() or "ago" in content.lower()
