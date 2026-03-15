"""Integration tests for perform_visual_action against a real browser.

Launches a real Playwright browser via the browser tools infrastructure,
loads a test HTML page, and calls perform_visual_action end-to-end —
hitting the real UI-TARS grounding server for action prediction.

Requires the inference container to be running.

UI-TARS is a single-step action predictor: each call returns ONE action.
Complex interactions (type, drag) require multiple calls, just like the
agent would use in production. Tests call perform_visual_action in a loop
with the same task until the desired page state is achieved or a step
budget is exhausted.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tools.browser import close_browser, open_url
from tools.browser.core import get_browser
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.vision import perform_visual_action

logger = logging.getLogger(__name__)

# Path to the test HTML fixture.
_TEST_PAGE = Path(__file__).resolve().parents[3] / "server" / "static" / "visual_action_test.html"

# Maximum steps to give TARS before giving up.
_MAX_STEPS = 5


@pytest.fixture(autouse=True)
async def _browser_lifecycle():
    """Ensure the singleton browser is shut down after each test."""
    yield
    await close_browser()


async def _open_test_page() -> str:
    """Navigate to the visual action test fixture and return the snapshot."""
    return await open_url(f"file://{_TEST_PAGE}")


async def _run_until(task: str, check_fn, *, max_steps: int = _MAX_STEPS) -> bool:
    """Call perform_visual_action repeatedly until check_fn returns True."""
    for step in range(max_steps):
        try:
            await perform_visual_action(task)
        except BrowserToolError:
            logger.warning("Step %d failed for task %r, retrying", step + 1, task)
            continue
        if await check_fn():
            logger.info("Task %r succeeded at step %d", task, step + 1)
            return True
    return False


# ── Click ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_click_via_vision() -> None:
    """perform_visual_action should click the blue 'Click Me' button."""
    await _open_test_page()
    browser = await get_browser()
    page = await browser.current_page()

    async def _was_clicked() -> bool:
        return await page.locator("#click-status").inner_text() == "Clicked!"

    success = await _run_until("Click the blue 'Click Me' button", _was_clicked)
    assert success, "TARS did not click the button within step budget"


# ── Type (multi-step: TARS clicks first, then types) ─────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_type_via_vision() -> None:
    """perform_visual_action should type text into an input field.

    TARS needs visual evidence that a field is active before it predicts
    ``type`` — a focused-but-empty field looks identical to an unfocused
    one in a screenshot (no cursor visible in headless mode). So we use
    TARS to click the field, seed one character so the cursor is visible,
    then ask TARS to continue typing.
    """
    await _open_test_page()
    browser = await get_browser()
    page = await browser.current_page()

    # Step 1: Click the input via vision to focus it.
    await perform_visual_action("Click on the text input field")

    # Seed a character so TARS can visually see the field is active.
    await page.keyboard.type("H")

    # Step 2: Now TARS should predict type() since it can see text in the field.
    async def _has_typed() -> bool:
        value = await page.locator("#type-input").input_value()
        return len(value) > 1  # More than just the seeded "H"

    success = await _run_until(
        "Continue typing 'ello world' into the text input field",
        _has_typed,
    )
    assert success, "TARS did not type into the input within step budget"

    value = await page.locator("#type-input").input_value()
    assert "ello" in value.lower(), f"Expected typed text, got {value!r}"


# ── Scroll ────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scroll_via_vision() -> None:
    """perform_visual_action should scroll the page down."""
    await _open_test_page()
    browser = await get_browser()
    page = await browser.current_page()

    async def _scrolled() -> bool:
        return await page.evaluate("() => window.scrollY") > 0

    success = await _run_until("Scroll down on this page", _scrolled)
    assert success, "TARS did not scroll down within step budget"


# ── Drag (scroll into view first) ────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drag_via_vision() -> None:
    """perform_visual_action should drag the red square to the drop zone."""
    await _open_test_page()

    browser = await get_browser()
    page = await browser.current_page()
    await page.locator("#section-drag").scroll_into_view_if_needed()

    async def _was_dragged() -> bool:
        status = await page.locator("#drag-status").inner_text()
        return status != "Not dragged"

    success = await _run_until(
        "Drag the red square labeled 'Drag' and drop it into the dashed 'Drop here' box",
        _was_dragged,
    )
    assert success, "TARS did not attempt a drag within step budget"
