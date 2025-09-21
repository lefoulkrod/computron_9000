"""Tool that captures the current page screenshot and answers a visual question."""

import logging
import re
from base64 import b64encode
from collections.abc import Iterable
from typing import Literal

from ollama import AsyncClient, Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from config import load_config
from models.model_configs import get_model_by_name
from tools.browser.core import get_browser
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


def _normalize_selector_expression(raw: str) -> str:
    """Normalize a single selector expression.

    Currently translates the common hallucinated ``:contains("text")`` into Playwright's
    ``:has-text("text")`` form. Only simple string literal cases (single or double quotes)
    are handled; anything more complex is left unchanged.
    """
    pattern = re.compile(r":contains\((['\"])(.+?)\1\)")
    # Replace each occurrence cautiously
    return pattern.sub(r":has-text(\1\2\1)", raw)


def _expand_selector_candidates(selector: str) -> list[str]:
    """Expand a potentially comma-delimited selector string into ordered candidates.

    Each candidate is normalized. Empty segments are discarded.
    """
    parts = [s.strip() for s in selector.split(",")]
    cleaned: list[str] = []
    for part in parts:
        if not part:
            continue
        cleaned.append(_normalize_selector_expression(part))
    return cleaned or [selector]


async def _attempt_selector_screenshots(page: Page, candidates: Iterable[str]) -> bytes:
    """Try each selector candidate until one yields a screenshot.

    Args:
        page: Playwright page instance.
        candidates: Iterable of selector strings.

    Returns:
        PNG bytes of the first successfully captured element screenshot.

    Raises:
        BrowserToolError: If none of the candidates matched or screenshot fails.
    """
    last_error: Exception | None = None
    tried: list[str] = []
    for cand in candidates:
        tried.append(cand)
        try:
            locator = page.locator(cand).first  # Playwright locator
            found_count = await locator.count()
            if found_count == 0:
                continue
            return await locator.screenshot(type="png")
        except Exception as exc:  # noqa: BLE001 - broad to aggregate candidate failures
            last_error = exc
            continue
    msg = "No elements matched any selector candidate. Tried: " + ", ".join(tried)
    if last_error is not None:
        msg += f"; last error type: {type(last_error).__name__}: {last_error}"
    raise BrowserToolError(msg, tool="ask_about_screenshot")


async def ask_about_screenshot(
    prompt: str,
    *,
    mode: Literal["full_page", "viewport", "selector"] = "full_page",
    selector: str | None = None,
) -> str:
    r"""Answer a prompt about the active page by capturing a screenshot.

    Args:
        prompt: Question the model should answer about the screenshot.
        mode: Screenshot mode - one of {"full_page", "viewport", "selector"}.
        selector: When ``mode="selector"``, an element selector. Supports comma-separated
            candidates. ``:contains("text")`` will be translated to ``:has-text("text")``.

    Selector examples (standard CSS only - do not use framework-specific pseudo-selectors):
        - "#hero-banner"
        - ".cta.primary"
        - "button.primary"
        - "a[href*='login']"
        - "#pricing, .plan-tier:first-of-type" (tries in order)

    Notes:
        - Provide ONLY standard CSS. Do NOT invent non-standard pseudo-classes like :contains().
        - If you need to target text, choose a structural selector (e.g., a class, id, attribute)
          instead of a text-based pseudo-class.

    Returns:
        The model's answer as a plain string.

    Raises:
        BrowserToolError: On validation, browser, screenshot, or model failures. The error
        message is intentionally specific so the calling LLM can adjust its next attempt.
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        msg = "Prompt must be a non-empty string."
        raise BrowserToolError(msg, tool="ask_about_screenshot")

    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"full_page", "viewport", "selector"}:
        msg = "mode must be one of {'full_page', 'viewport', 'selector'}."
        raise BrowserToolError(msg, tool="ask_about_screenshot")

    def _get_validated_selector() -> str:
        """Get and validate selector for selector mode.

        Returns:
            The cleaned selector string.

        Raises:
            BrowserToolError: If selector is missing or empty when mode='selector'.
        """
        if selector is None or not selector.strip():
            msg = "selector must be provided when mode='selector'."
            raise BrowserToolError(msg, tool="ask_about_screenshot")
        return selector.strip()

    if normalized_mode == "selector":
        selector = _get_validated_selector()

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
            candidates = _expand_selector_candidates(selector)
            screenshot_bytes = await _attempt_selector_screenshots(page, candidates)
        elif normalized_mode == "full_page":
            screenshot_bytes = await page.screenshot(type="png", full_page=True)
        else:  # viewport
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
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
