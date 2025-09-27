"""Answer visual questions about the active browser page by capturing screenshots.

This module provides a single async function `ask_about_screenshot` which captures
either a full-page, viewport, or element screenshot and sends it to a vision
model for analysis.

The public function follows the project's error-wrapping conventions and raises
``BrowserToolError`` for validation, browser, screenshot, or model failures.
"""

import logging
from base64 import b64encode
from typing import Literal

from ollama import AsyncClient, Image
from playwright.async_api import Error as PlaywrightError

from config import load_config
from models.model_configs import get_model_by_name
from tools.browser.core import get_browser
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


async def ask_about_screenshot(
    prompt: str,
    *,
    mode: Literal["full_page", "viewport", "selector"] = "full_page",
    selector: str | None = None,
) -> str:
    """Capture a screenshot and ask a vision model a question about it.

    Args:
        prompt: Question the model should answer about the screenshot.
        mode: One of ``"full_page"``, ``"viewport"``, or ``"selector"``. Determines
            which area of the page to capture.
        selector: When ``mode == "selector"``, a CSS selector targeting the element to capture.

    Returns:
        The model's answer as a plain string.

    Raises:
        BrowserToolError: If the prompt is empty, the page is not navigated, the selector is
            invalid or missing when required, screenshot capture fails, or model generation fails.
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        msg = "Prompt must be a non-empty string."
        raise BrowserToolError(msg, tool="ask_about_screenshot")

    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"full_page", "viewport", "selector"}:
        msg = "mode must be one of {'full_page', 'viewport', 'selector'}."
        raise BrowserToolError(msg, tool="ask_about_screenshot")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except Exception as exc:  # pragma: no cover - defensive wiring guard
        logger.exception("Unable to access browser page for screenshot")
        msg = "Unable to access browser page."
        raise BrowserToolError(msg, tool="ask_about_screenshot") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before asking about its screenshot."
        raise BrowserToolError(msg, tool="ask_about_screenshot")

    try:
        if normalized_mode == "selector":
            if selector is None:
                msg = "selector cannot be None when mode='selector'."
                raise BrowserToolError(msg, tool="ask_about_screenshot")
            clean_selector = selector.strip()
            if not clean_selector:
                msg = "selector must be a non-empty string when mode='selector'."
                raise BrowserToolError(msg, tool="ask_about_screenshot")
            resolution = await _resolve_locator(
                page,
                clean_selector,
                allow_substring_text=False,
                require_single_match=True,
                tool_name="ask_about_screenshot",
            )
            if resolution is None:
                msg = f"No element matched selector '{clean_selector}'"
                raise BrowserToolError(msg, tool="ask_about_screenshot")
            locator = resolution.locator
            screenshot_bytes = await locator.screenshot(type="png")
        elif normalized_mode == "full_page":
            screenshot_bytes = await page.screenshot(type="png", full_page=True)
        else:  # viewport
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to capture screenshot for page %s", page.url)
        # Surface underlying Playwright message for LLM adaptability.
        err_msg = f"Playwright error capturing screenshot: {exc}"
        raise BrowserToolError(err_msg, tool="ask_about_screenshot") from exc
    except Exception as exc:  # pragma: no cover - unexpected Playwright failure
        logger.exception("Unexpected failure capturing screenshot for page %s", page.url)
        err_msg = f"Unexpected failure capturing screenshot: {exc}"
        raise BrowserToolError(err_msg, tool="ask_about_screenshot") from exc

    encoded_image = b64encode(screenshot_bytes).decode("ascii")

    try:
        model = get_model_by_name("vision")
    except Exception as exc:  # pragma: no cover - configuration guard
        logger.exception("Vision model configuration missing")
        msg = "Vision model configuration missing."
        raise BrowserToolError(msg, tool="ask_about_screenshot") from exc

    config = load_config()
    host = getattr(getattr(config, "llm", None), "host", None)
    client = AsyncClient(host=host) if host else AsyncClient()

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
        raise BrowserToolError(msg, tool="ask_about_screenshot") from exc

    return response.response


__all__ = [
    "ask_about_screenshot",
]
