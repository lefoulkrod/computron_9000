"""Vision-enabled browser tools built on top of the shared Ollama model."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, cast

from ollama import AsyncClient, Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import load_config
from tools.browser.core import get_active_view, get_browser
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError

_BBOX_DEBUG_ENV = "COMPUTRON_VISION_DEBUG"
_BBOX_OVERLAY_SCRIPT = """
((bbox) => {
  const [x1, y1, x2, y2] = bbox;
  const id = '__vision_bbox_overlay__';
  const remove = () => {
    const existing = document.getElementById(id);
    if (existing) existing.remove();
  };
  remove();
  if (!Array.isArray(bbox) || bbox.length !== 4) return;
  const overlay = document.createElement('div');
  overlay.id = id;
  overlay.style.position = 'fixed';
  overlay.style.left = `${x1}px`;
  overlay.style.top = `${y1}px`;
  overlay.style.width = `${Math.max(0, x2 - x1)}px`;
  overlay.style.height = `${Math.max(0, y2 - y1)}px`;
  overlay.style.border = '2px solid #ff0062';
  overlay.style.background = 'rgba(255, 0, 98, 0.15)';
  overlay.style.pointerEvents = 'none';
  overlay.style.zIndex = '2147483647';
  document.body.appendChild(overlay);
})
"""

logger = logging.getLogger(__name__)

_SCREENSHOT_TOOL_NAME = "ask_about_screenshot"
_GROUNDING_TOOL_NAME = "ground_elements_by_text"
_PROMPT_TEMPLATE = """You are a precise UI element locator. Find elements in a screenshot using normalized 0-1000 coordinates.

TASK: Find ALL elements matching: {text_json}

COORDINATE SYSTEM:
- Scale: 0 to 1000 where (0,0) is top-left, (1000,1000) is bottom-right
- Format: [x1, y1, x2, y2] where x1=left, y1=top, x2=right, y2=bottom

Return ONLY a JSON array. No markdown, no code fences, no explanation.
[{{"text": "visible text", "bbox": [x1, y1, x2, y2]}}]

Return [] if nothing matches."""


class GroundingResult(BaseModel):
    """Result for a grounded UI element.

    Fields:
        text: visible text the model matched
        bbox: (x1, y1, x2, y2) viewport pixel coordinates — pass directly to click_at/press_and_hold_at
        center: (x, y) center point of the bbox for reference
        reasoning: optional spatial reasoning from the vision model
    """

    text: str | None = Field(default=None)
    bbox: tuple[int, int, int, int]
    center: tuple[int, int] = Field(default=(0, 0))
    reasoning: str | None = None

    model_config = ConfigDict(extra="forbid")


async def ask_about_screenshot(
    prompt: str,
    *,
    mode: str = "full_page",
    selector: str | None = None,
) -> str:
    """Ask a vision model a question about the current page.  SLOW.

    Sends a screenshot to a vision model and returns its TEXT answer.
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

    return answer


async def ground_elements_by_text(description: str) -> list[GroundingResult]:
    """Get the bounding boxes of all elements matching the given description.

    This tool uses a vision model to locate UI elements on the current page.
    For best results, provide descriptive prompts with spatial context and
    visual details.

    Prompting Best Practices:
        - Include element type: "button", "link", "input", "card", "badge", "table"
        - Add spatial context: "in the top-right corner", "below the header", "left sidebar"
        - Mention colors: "blue Book button", "green status badge", "yellow card"
        - Reference nearby elements: "next to the price", "under the title"
        - Include visible text when available: "button with text 'Submit'"

    Good Examples:
        - "blue Book button next to the Beard Trim service price"
        - "table showing Latency, Throughput, and Uptime metrics in lower left"
        - "purple Notify Me button below the email input field"
        - "Status badge in cyan color in the second panel"

    Poor Examples (too vague):
        - "button" (which button? there may be many)
        - "the table" (describe location or distinctive content)
        - "Book" (is it a button, link, or text? where is it?)

    Args:
        description: Descriptive text with spatial/visual details to locate the element(s).
            The model returns ALL matching elements, so be specific to avoid duplicates.

    Returns:
        list[GroundingResult]: Bounding boxes with element metadata from the vision model.
            Each result includes bbox (pass directly to click_at/press_and_hold_at),
            center, resolved selector, and reasoning.
            Multiple elements may be returned if the description matches several locations.

    Raises:
        BrowserToolError: If the page is inaccessible, the screenshot fails, or the
        vision model response is invalid.
    """
    clean_text = description.strip()
    if not clean_text:
        msg = "visible_text must be a non-empty string."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME)

    _browser, view = await get_active_view(_GROUNDING_TOOL_NAME)
    # Screenshots require the Page object (not Frame)
    page = await _browser.current_page()

    try:
        # Always use viewport screenshots for grounding
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
    except PlaywrightError as exc:
        logger.exception("Failed to capture screenshot for grounding request on %s", page.url)
        msg = "Failed to capture screenshot for grounding request."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc
    except Exception as exc:  # pragma: no cover - unexpected Playwright failure
        logger.exception("Unexpected failure capturing screenshot for grounding request on %s", page.url)
        msg = "Unexpected failure capturing screenshot."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

    width_px = height_px = 0
    try:
        viewport_size = getattr(page, "viewport_size", None)
        if isinstance(viewport_size, dict):
            width_px = int(viewport_size.get("width") or 0)
            height_px = int(viewport_size.get("height") or 0)
    except (TypeError, ValueError) as exc:
        # viewport width/height weren't numeric or convertible to int
        logger.debug("Unable to read viewport_size: %s", exc)
        width_px = height_px = 0

    logger.debug("Viewport size: %dx%d CSS pixels", width_px, height_px)

    encoded_image = _encode_image(screenshot_bytes)

    client, model = _make_vision_client(tool_name=_GROUNDING_TOOL_NAME)
    prompt = _render_prompt(clean_text)
    logger.debug("Grounding prompt: %s", prompt)
    try:
        response = await client.generate(
            model=model.model,
            prompt=prompt,
            options=model.options,
            images=[Image(value=encoded_image)],
            think=model.think,
        )
    except Exception as exc:
        logger.exception("Failed to generate grounding response from vision model")
        msg = "Failed to generate grounding response from vision model."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

    raw_response = (response.response or "").strip()
    logger.debug("Raw grounding response from model: %s", raw_response)
    logger.debug("Viewport dimensions: %dx%d", width_px, height_px)

    def _extract_json_text(s: str) -> str:
        """Try to extract a JSON payload from the model response.

        Handles plain JSON, code-fenced JSON (```json ... ```), or surrounding text
        by attempting a few heuristics in order.
        """
        text = s.strip()
        # Remove wrapping triple backticks and optional language e.g. ```json
        if text.startswith("```") and text.endswith("```"):
            inner = text[3:-3].strip()
            # If the inner starts with a language token like 'json', strip it
            if inner.startswith("json"):
                inner = inner[4:].strip()
            return inner

        # If not fenced, but contains fenced block somewhere, extract inside first fence
        if "```" in text:
            parts = text.split("```")
            # parts like [pre, fencecontent, post, ...] - take the first fenced content
            for i in range(1, len(parts), 2):
                candidate = parts[i].strip()
                if candidate:
                    # strip leading language token if present
                    if candidate.startswith("json"):
                        candidate = candidate[4:].strip()
                    return candidate

        # Fallback: try to extract the first JSON array by finding the first '[' and the matching ']'
        first = text.find("[")
        last = text.rfind("]")
        if first != -1 and last != -1 and last > first:
            return text[first : last + 1]

        # Otherwise return original
        return text

    cleaned = _extract_json_text(raw_response)

    # Handle empty response (model found nothing or failed to respond)
    if not cleaned or cleaned.strip() == "":
        logger.warning("Vision model returned empty response for grounding request")
        return []

    def _repair_json(text: str) -> str:
        """Attempt to repair common JSON syntax errors from vision models."""
        # Fix missing closing bracket in bbox arrays: [x,y,w,h"} -> [x,y,w,h]}
        # Pattern: array with 4 numbers followed by "}] instead of ]}
        text = re.sub(r'(\[\d+,\d+,\d+,\d+)"\}', r"\1]}", text)
        return text

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Try to repair common JSON errors and parse again
        repaired = _repair_json(cleaned)
        if repaired != cleaned:
            logger.debug("Attempting to repair malformed JSON: %s -> %s", cleaned, repaired)
            try:
                parsed = json.loads(repaired)
                logger.info("Successfully repaired and parsed JSON")
            except json.JSONDecodeError:
                logger.exception("Vision model returned invalid JSON for grounding request")
                msg = "Vision model returned invalid JSON."
                raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc
        else:
            logger.exception("Vision model returned invalid JSON for grounding request")
            msg = "Vision model returned invalid JSON."
            raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

    if not isinstance(parsed, list):
        msg = "Vision model response must be a list of bounding boxes."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME)

    # Handle bare bbox: model returned [x1, y1, x2, y2] instead of [{"bbox": [...]}]
    if parsed and all(isinstance(v, (int, float)) for v in parsed):
        if len(parsed) == 4:
            parsed = [{"bbox": parsed}]
        else:
            msg = "Vision model returned a flat numeric list that is not a valid bbox (expected 4 values)."
            raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME)

    results: list[GroundingResult] = []
    for entry in parsed:
        try:
            # Vision models return bounding boxes under varying field names
            # depending on the model (e.g. "bbox", "bbox_2d", "bounding_box").
            bbox_raw = entry.get("bbox") or entry.get("bbox_2d") or entry.get("bounding_box")
            if isinstance(bbox_raw, str):
                parts = [p.strip() for p in bbox_raw.split(",") if p.strip()]
                bbox_raw = parts
            if not isinstance(bbox_raw, (list | tuple)) or len(bbox_raw) != 4:
                raise ValueError("bbox must be a sequence of four numbers")
            try:
                # Model returns [x1, y1, x2, y2] in normalized coordinates (0-1000)
                # Convert to CSS pixels using viewport dimensions
                x1_norm, y1_norm, x2_norm, y2_norm = (float(v) for v in bbox_raw)

                x1 = round((x1_norm / 1000) * width_px)
                y1 = round((y1_norm / 1000) * height_px)
                x2 = round((x2_norm / 1000) * width_px)
                y2 = round((y2_norm / 1000) * height_px)
            except (TypeError, ValueError) as exc:
                raise ValueError("bbox values must be numeric") from exc

            logger.debug(
                "Parsed bbox from model (normalized): [%.1f, %.1f, %.1f, %.1f] -> CSS px: [%d, %d, %d, %d]",
                x1_norm, y1_norm, x2_norm, y2_norm,
                x1, y1, x2, y2,
            )

            cx = round((x1 + x2) / 2)
            cy = round((y1 + y2) / 2)

            validated = GroundingResult.model_validate(
                {
                    "text": entry.get("text") or entry.get("label"),
                    "bbox": (x1, y1, x2, y2),
                    "center": (cx, cy),
                    "reasoning": entry.get("reasoning"),
                },
                strict=False,
            )
        except (ValidationError, ValueError) as exc:
            logger.exception("Vision model produced an invalid grounding entry: %s", entry)
            msg = "Vision model returned invalid bounding box entries."
            raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

        # Optional debug overlay
        if os.getenv(_BBOX_DEBUG_ENV):
            try:
                await view.frame.evaluate(_BBOX_OVERLAY_SCRIPT, list(validated.bbox))
            except PlaywrightError:
                logger.debug("Failed to inject bbox overlay for %s", validated.bbox)

        results.append(validated)

    return results


async def _selector_screenshot(page: Page, selector: str | None) -> bytes:
    # Deprecated in simplified grounding API; kept for screenshot tool only.
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
    # The Ollama AsyncClient expects base64-encoded image payloads.
    return base64.b64encode(image_bytes).decode("ascii")


def _render_prompt(visible_text: str) -> str:
    """Build the grounding prompt with JSON-compliant quoting."""
    quoted = json.dumps(visible_text)
    return _PROMPT_TEMPLATE.format(text_json=quoted)


async def click_element(description: str) -> str:
    """Visually locate a UI element by description and click it.

    Combines grounding (vision model) with a coordinate click in one step.
    Use this when ``browse_page`` selectors can't find the element (shadow DOM,
    iframes, dynamically injected content, bot challenges).

    Args:
        description: Descriptive text with spatial/visual details to locate the
            element. Follow the same prompting best practices as
            ``ground_elements_by_text``.

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If no element is found or the click fails.
    """
    from tools.browser.core.human import human_click_at
    from tools.browser.interactions import _format_result

    results = await ground_elements_by_text(description)
    if not results:
        raise BrowserToolError(
            f"No elements found matching: {description!r}",
            tool="click_element",
        )

    best = results[0]
    browser, view = await get_active_view("click_element")

    try:
        result = await browser.perform_interaction(lambda: human_click_at(view.frame, *best.bbox))
        return await _format_result(result)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover
        logger.exception("click_element failed for %r at bbox %s", description, best.bbox)
        raise BrowserToolError("click_element failed", tool="click_element") from exc


async def press_and_hold_element(
    description: str,
    duration_ms: int = 3000,
) -> str:
    """Visually locate a UI element by description and press-and-hold it.

    Combines grounding (vision model) with a coordinate press-and-hold in one
    step. Use this for bot-detection challenges and any hold interactions when
    selectors can't reach the element.

    Args:
        description: Descriptive text with spatial/visual details to locate the
            element.
        duration_ms: How long to hold the mouse button in milliseconds.
            Defaults to 3000 (3 seconds). Range: 500-10000.

    Returns:
        Updated page snapshot string after the hold is released.

    Raises:
        BrowserToolError: If no element is found or the hold fails.
    """
    from tools.browser.core.human import human_press_and_hold_at
    from tools.browser.interactions import _format_result

    results = await ground_elements_by_text(description)
    if not results:
        raise BrowserToolError(
            f"No elements found matching: {description!r}",
            tool="press_and_hold_element",
        )

    best = results[0]
    clamped = max(500, min(10000, duration_ms))
    browser, view = await get_active_view("press_and_hold_element")

    try:
        result = await browser.perform_interaction(
            lambda: human_press_and_hold_at(view.frame, *best.bbox, duration_ms=clamped),
        )
        return await _format_result(result)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover
        logger.exception("press_and_hold_element failed for %r at bbox %s", description, best.bbox)
        raise BrowserToolError(
            "press_and_hold_element failed", tool="press_and_hold_element",
        ) from exc


__all__ = [
    "ask_about_screenshot",
    "click_element",
    "ground_elements_by_text",
    "press_and_hold_element",
]
