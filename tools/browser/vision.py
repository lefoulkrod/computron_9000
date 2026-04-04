"""Vision-enabled browser tools.

Uses Ollama for visual question answering (``inspect_page``) and the
UI-TARS grounding server for action prediction (``browser_visual_action``).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, cast

from ollama import AsyncClient, Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict, Field

from config import load_config
from tools.browser.core import get_active_view, get_browser
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.events import emit_screenshot_after

logger = logging.getLogger(__name__)

_SCREENSHOT_TOOL_NAME = "inspect_page"
_VISUAL_ACTION_TOOL_NAME = "browser_visual_action"


async def inspect_page(
    prompt: str,
    *,
    mode: str = "full_page",
    selector: str | None = None,
) -> str:
    """Inspect the current page visually and answer a question about it.  SLOW.

    Captures a screenshot and sends it to a vision model with your prompt.
    You never receive the image — only the model's text response.
    Be specific in your prompt to get structured, usable answers:
        GOOD: "List every item in the grid as row,col: value."
        GOOD: "What color is each cell? Format: position → color."
        GOOD: "Read the text shown in the image/canvas element."
        BAD:  "What does the page look like?" (too vague)

    Args:
        prompt: Specific question about what you see on the page.
        mode: ``"full_page"`` (default), ``"viewport"``, or ``"selector"``.
        selector: Required when ``mode="selector"`` — ref number of the
            element to capture.

    Returns:
        A text answer from the vision model (never an image).

    Raises:
        BrowserToolError: If capture or model generation fails.
    """
    t0 = asyncio.get_event_loop().time()

    clean_prompt = prompt.strip()
    if not clean_prompt:
        msg = "Prompt must be a non-empty string."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"full_page", "viewport", "selector"}:
        msg = "mode must be one of {'full_page', 'viewport', 'selector'}."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    _browser, view = await get_active_view(_SCREENSHOT_TOOL_NAME)
    # Screenshots require the Page object (not Frame)
    page = await _browser.current_page()

    try:
        if normalized_mode == "selector":
            screenshot_bytes = await _selector_screenshot(page, selector)
        elif normalized_mode == "full_page":
            screenshot_bytes = await page.screenshot(type="png", full_page=True)
        else:  # viewport
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to capture screenshot for page %s", page.url)
        err_msg = f"Playwright error capturing screenshot: {exc}"
        raise BrowserToolError(err_msg, tool=_SCREENSHOT_TOOL_NAME) from exc
    except Exception as exc:  # pragma: no cover - unexpected Playwright failure
        logger.exception("Unexpected failure capturing screenshot for page %s", page.url)
        err_msg = f"Unexpected failure capturing screenshot: {exc}"
        raise BrowserToolError(err_msg, tool=_SCREENSHOT_TOOL_NAME) from exc

    encoded_image = _encode_image(screenshot_bytes)

    client, model = _make_vision_client(tool_name=_SCREENSHOT_TOOL_NAME)

    try:
        response = await client.generate(
            model=model.model,
            prompt=clean_prompt,
            options=model.options,
            images=[Image(value=encoded_image)],
            think=model.think,
        )
    except Exception as exc:
        logger.exception("Failed to generate answer for screenshot question")
        msg = "Failed to generate answer from screenshot."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME) from exc

    answer = cast(str | None, getattr(response, "response", None))
    if answer is None:
        msg = "Vision model did not return an answer."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    from tools._vision_logging import log_vision_panel

    elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
    log_vision_panel(
        "inspect_page", model.model,
        clean_prompt, answer, elapsed_ms,
        image_source="%s (%s)" % (view.url, normalized_mode),
    )

    return answer


@emit_screenshot_after
async def browser_visual_action(task: str) -> str:
    """Ask a vision model to decide and execute the next GUI action.

    Only the current viewport is screenshotted — the target element must
    be visible on screen. Scroll it into view first if necessary.

    Supported actions (chosen automatically by the model): click,
    double-click, right-click, drag, type text, hotkey, scroll, and wait.

    Args:
        task: Natural-language description of what to do, e.g.
            ``"Click the Login button"``, ``"Drag the slider to the right"``,
            or ``"Type hello into the search box"``.

    Returns:
        Updated page snapshot string after executing the action.

    Raises:
        BrowserToolError: If the page is inaccessible, the screenshot fails,
            the grounding server is unreachable, or the action fails.
    """
    from tools._grounding import run_grounding
    from tools.browser._action_map import execute_action
    from tools.browser.interactions import _format_result

    clean_task = task.strip()
    if not clean_task:
        msg = "task must be a non-empty string."
        raise BrowserToolError(msg, tool=_VISUAL_ACTION_TOOL_NAME)

    browser, view = await get_active_view(_VISUAL_ACTION_TOOL_NAME)
    page = await browser.current_page()

    # Capture viewport screenshot.
    try:
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
    except PlaywrightError as exc:
        logger.exception("Failed to capture screenshot for visual action on %s", page.url)
        msg = "Failed to capture screenshot for visual action."
        raise BrowserToolError(msg, tool=_VISUAL_ACTION_TOOL_NAME) from exc

    # Send to grounding server.
    try:
        response = await run_grounding(
            screenshot_bytes,
            clean_task,
            screenshot_filename="browser_visual_action.png",
        )
    except RuntimeError as exc:
        logger.exception("Grounding request failed for %r", clean_task)
        msg = "Grounding request failed: %s" % exc
        raise BrowserToolError(msg, tool=_VISUAL_ACTION_TOOL_NAME) from exc

    logger.info(
        "Visual action: %s → %s (thought: %s)",
        clean_task, response.action_type, response.thought,
    )

    # Handle finished — return snapshot with note.
    if response.action_type == "finished":
        finished_content = response.raw.get("finished_content", "")
        from tools.browser.core._formatting import format_page_view
        from tools.browser.core.page_view import build_page_view

        snapshot = await build_page_view(view, None)
        content = snapshot.content
        if finished_content:
            content += "\n\n--- Vision model says task is finished: %s ---" % finished_content
        return format_page_view(
            title=snapshot.title,
            url=snapshot.url,
            status_code=snapshot.status_code,
            viewport=snapshot.viewport,
            content=content,
            truncated=snapshot.truncated,
        )

    # Execute the action via perform_interaction for proper settle/snapshot.
    try:
        result = await browser.perform_interaction(
            lambda: execute_action(response, page, view.frame),
        )
        return await _format_result(result, tool_name=_VISUAL_ACTION_TOOL_NAME)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Visual action execution failed for %r", clean_task)
        msg = "Visual action execution failed: %s" % exc
        raise BrowserToolError(msg, tool=_VISUAL_ACTION_TOOL_NAME) from exc


async def _selector_screenshot(page: Page, selector: str | None) -> bytes:
    if selector is None:
        msg = "selector cannot be None when mode='selector'."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string when mode='selector'."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    # Use active frame for locator resolution (element may be inside an iframe)
    browser = await get_browser()
    active_view = await browser.active_view()

    resolution = await _resolve_locator(
        active_view.frame,
        clean_selector,
        tool_name=_SCREENSHOT_TOOL_NAME,
    )
    if resolution is None:
        msg = f"No element matched selector handle '{clean_selector}'"
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)
    locator = resolution.locator
    return await locator.screenshot(type="png")


def _make_vision_client(*, tool_name: str) -> tuple[AsyncClient, Any]:
    """Return a configured AsyncClient and model tuple for the shared vision model."""
    config = load_config()
    if config.vision is None:
        msg = "Vision model configuration missing."
        raise BrowserToolError(msg, tool=tool_name)

    host = getattr(getattr(config, "llm", None), "host", None)
    client = AsyncClient(host=host) if host else AsyncClient()

    return client, config.vision


def _encode_image(image_bytes: bytes) -> str:
    """Encode screenshot bytes in base64 for the vision model."""
    return base64.b64encode(image_bytes).decode("ascii")


__all__ = [
    "inspect_page",
    "browser_visual_action",
]
