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
from models.model_configs import get_model_by_name
from tools.browser.core import get_browser
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.selectors import SelectorRegistry, build_unique_selector

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
_PROMPT_TEMPLATE = """
You are a precise UI element locator. Your task is to ground elements in a 1000x1000 normalized coordinate system.

TASK: Find ALL elements matching: {text_json}
SCREENSHOT DIMENSIONS: {width}px x {height}px (for reference only)

COORDINATE SYSTEM:
- Normalized Scale: 0 to 1000 (0,0 is top-left; 1000,1000 is bottom-right)
- Format: [y1, x1, y2, x1] where y1=top, x1=left, y2=bottom, x2=right
- Think of the screen as a 1000x1000 grid regardless of actual pixel dimensions

OUTPUT FORMAT:
Return ONLY a JSON array of objects. Do not include markdown, code fences, or prose.
[
  {{
    "reasoning": "Brief spatial description (e.g., 'Blue submit button in center-right of footer')",
    "text": "visible text",
    "element_type": "button",
    "bbox": [y1, x1, y2, x2]
  }}
]

Return [] if nothing matches.

RULES:
1. SPATIAL REASONING FIRST: Before providing bbox, describe where the element is in the 1000x1000 grid
2. BOX TIGHTNESS: Include the entire clickable area (padding, borders, shadows)
3. CLICKABLE CENTER: The exact middle of your bbox [(y1+y2)/2, (x1+x2)/2] will be the click target
4. COORDINATE ORDER: Always use [y1, x1, y2, x2] format (height-first)
5. NO HALLUCINATION: If text is not clearly visible in the image, do not return a box
6. MATCHING: Case-insensitive text matching; match partial text if clearly the same element
7. ALL INSTANCES: Return ALL visible occurrences of the matching text

ELEMENT TYPES:
- button: clickable button elements
- link: anchor/hyperlink elements
- input: form input fields, textareas
- card: card/panel containers with content
- badge: small label/badge elements
- icon: icon-only elements
- text: plain text spans

Sort results: top-to-bottom.
"""


class GroundingResult(BaseModel):
    """Result for a grounded UI element.

    Fields:
        text: visible text the model matched
        bbox: (x1, y1, x2, y2) viewport pixel coordinates (top-left, bottom-right)
        selector: best-effort selector handle resolved from the page at the bbox center
        reasoning: optional spatial reasoning from the vision model
    """

    text: str | None = Field(default=None)
    bbox: tuple[int, int, int, int]
    selector: str | None = None
    reasoning: str | None = None

    model_config = ConfigDict(extra="forbid")


async def ask_about_screenshot(
    prompt: str,
    *,
    mode: str = "full_page",
    selector: str | None = None,
) -> str:
    """Capture a screenshot and ask the vision model a question about it.

    Args:
        prompt: Question the model should answer about the screenshot.
        mode: One of ``"full_page"``, ``"viewport"``, or ``"selector"``. Determines
            which area of the page to capture.
        selector: When ``mode == "selector"``, visible text on the element or a selector
            handle returned by page snapshots and other tools. The provided text or
            selector must uniquely identify the element to capture.

    Returns:
        The model's answer as a plain string.

    Raises:
        BrowserToolError: If the prompt is empty, the page is not navigated, the selector is
            invalid or missing when required, screenshot capture fails, or model generation fails.
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        msg = "Prompt must be a non-empty string."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"full_page", "viewport", "selector"}:
        msg = "mode must be one of {'full_page', 'viewport', 'selector'}."
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)

    page = await _get_active_page(
        tool_name=_SCREENSHOT_TOOL_NAME,
        blank_page_message="Navigate to a page before asking about its screenshot.",
    )

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
            Each result includes bbox coordinates, resolved selector, and reasoning.
            Multiple elements may be returned if the description matches several locations.

    Raises:
        BrowserToolError: If the page is inaccessible, the screenshot fails, or the
        vision model response is invalid.
    """
    clean_text = description.strip()
    if not clean_text:
        msg = "visible_text must be a non-empty string."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME)

    page = await _get_active_page(
        tool_name=_GROUNDING_TOOL_NAME,
        blank_page_message="Navigate to a page before requesting element grounding.",
    )

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
    prompt = _render_prompt(clean_text, width_px, height_px)
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

    # Create shared selector registry to ensure uniqueness across all grounded elements
    selector_registry = SelectorRegistry(page)

    results: list[GroundingResult] = []
    for entry in parsed:
        try:
            bbox_raw = entry.get("bbox")
            if isinstance(bbox_raw, str):
                parts = [p.strip() for p in bbox_raw.split(",") if p.strip()]
                bbox_raw = parts
            if not isinstance(bbox_raw, (list | tuple)) or len(bbox_raw) != 4:
                raise ValueError("bbox must be a sequence of four numbers")
            try:
                # Model returns [y1, x1, y2, x2] in normalized coordinates (0-1000)
                # Convert to CSS pixels using viewport dimensions
                y1_norm, x1_norm, y2_norm, x2_norm = (float(v) for v in bbox_raw)

                # Convert from normalized (0-1000) to CSS pixels
                # Formula: (normalized / 1000) * dimension
                x1 = round((x1_norm / 1000) * width_px)
                y1 = round((y1_norm / 1000) * height_px)
                x2 = round((x2_norm / 1000) * width_px)
                y2 = round((y2_norm / 1000) * height_px)
            except (TypeError, ValueError) as exc:
                raise ValueError("bbox values must be numeric") from exc

            logger.debug(
                "Parsed bbox from model (normalized): [%.1f, %.1f, %.1f, %.1f] -> CSS px: [%d, %d, %d, %d]",
                y1_norm,
                x1_norm,
                y2_norm,
                x2_norm,
                x1,
                y1,
                x2,
                y2,
            )

            validated = GroundingResult.model_validate(
                {
                    "text": entry.get("text"),
                    "bbox": (x1, y1, x2, y2),
                    "selector": None,
                    "reasoning": entry.get("reasoning"),
                },
                strict=False,
            )
        except (ValidationError, ValueError) as exc:
            logger.exception("Vision model produced an invalid grounding entry: %s", entry)
            msg = "Vision model returned invalid bounding box entries."
            raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

        # Resolve selector from bbox center using document.elementFromPoint via page.evaluate
        try:
            x1, y1, x2, y2 = validated.bbox
            # The center coordinates are in CSS pixels, matching what elementFromPoint expects
            cx = round((x1 + x2) / 2)
            cy = round((y1 + y2) / 2)

            if os.getenv(_BBOX_DEBUG_ENV):
                try:
                    await page.evaluate(_BBOX_OVERLAY_SCRIPT, [x1, y1, x2, y2])
                except PlaywrightError:
                    logger.debug("Failed to inject bbox overlay for %s", validated.bbox)

            # Call into the page to compute a selector handle for the element at the center.
            # We obtain the element at the bbox center via document.elementFromPoint
            # and then attempt registry-driven selector resolution for that handle.
            element_handle = None
            try:
                handle = await page.evaluate_handle(
                    "([x,y]) => document.elementFromPoint(x, y)",
                    [cx, cy],
                )
                element_handle = handle.as_element() if handle else None
            except PlaywrightError:
                logger.exception(
                    "document.elementFromPoint failed for bbox center %s,%s",
                    cx,
                    cy,
                )
            if element_handle is not None:
                try:
                    # Prefer registry-driven unique selector generation for grounding
                    # runs. Do not fallback to legacy helpers; if the registry fails
                    # record no selector for the grounded element.
                    try:
                        sel_res = await build_unique_selector(
                            element_handle, tag=None, text=validated.text or "", registry=selector_registry
                        )
                        selector_candidate = sel_res.selector
                    except Exception as exc:
                        logger.exception(
                            "SelectorRegistry failed during grounding selector resolution: %s",
                            exc,
                        )
                        selector_candidate = None

                    logger.debug(
                        "Grounding selector for bbox %s center %s,%s -> %s",
                        (x1, y1, x2, y2),
                        cx,
                        cy,
                        selector_candidate,
                    )
                    validated.selector = selector_candidate or None
                except PlaywrightError:
                    logger.exception(
                        "Selector resolution failed for bbox center %s,%s",
                        cx,
                        cy,
                    )
                finally:
                    try:
                        await element_handle.dispose()
                    except PlaywrightError:
                        logger.debug("Failed to dispose element_handle after grounding resolution")
        except PlaywrightError:
            # Guard selector resolution; don't abort the entire call if one entry fails to resolve
            logger.exception("Failed to resolve selector for grounding entry: %s", entry)

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

    resolution = await _resolve_locator(
        page,
        clean_selector,
        allow_substring_text=False,
        require_single_match=True,
        tool_name=_SCREENSHOT_TOOL_NAME,
    )
    if resolution is None:
        msg = f"No element matched selector handle '{clean_selector}'"
        raise BrowserToolError(msg, tool=_SCREENSHOT_TOOL_NAME)
    locator = resolution.locator
    return await locator.screenshot(type="png")


async def _get_active_page(*, tool_name: str, blank_page_message: str) -> Page:
    """Return the current Playwright page or raise a browser tool error."""
    try:
        browser = await get_browser()
        page = await browser.current_page()
    except Exception as exc:  # pragma: no cover - defensive wiring guard
        logger.exception("Unable to access browser page for tool %s", tool_name)
        msg = "Unable to access browser page."
        raise BrowserToolError(msg, tool=tool_name) from exc

    if page.url in {"", "about:blank"}:
        raise BrowserToolError(blank_page_message, tool=tool_name)

    return page


def _make_vision_client(*, tool_name: str) -> tuple[AsyncClient, Any]:
    """Return a configured AsyncClient and model tuple for the shared vision model."""
    try:
        model = get_model_by_name("vision")
    except Exception as exc:  # pragma: no cover - configuration guard
        logger.exception("Vision model configuration missing for tool %s", tool_name)
        msg = "Vision model configuration missing."
        raise BrowserToolError(msg, tool=tool_name) from exc

    config = load_config()
    host = getattr(getattr(config, "llm", None), "host", None)
    client = AsyncClient(host=host) if host else AsyncClient()

    return client, model


def _encode_image(image_bytes: bytes) -> str:
    """Encode screenshot bytes in base64 for the vision model."""
    # The Ollama AsyncClient expects base64-encoded image payloads.
    return base64.b64encode(image_bytes).decode("ascii")


def _scale_to_viewport(normalized_coord: int, viewport_dimension: int) -> int:
    """Scale a normalized 0-1000 coordinate to viewport pixel dimension.

    Args:
        normalized_coord: Coordinate value in the 0-1000 normalized range.
        viewport_dimension: The viewport dimension (width or height) in pixels.

    Returns:
        The scaled coordinate as an integer pixel value.
    """
    return int((normalized_coord / 1000) * viewport_dimension)


def _render_prompt(visible_text: str, width: int, height: int) -> str:
    """Build the grounding prompt with JSON-compliant quoting and viewport dimensions."""
    quoted = json.dumps(visible_text)
    return _PROMPT_TEMPLATE.format(text_json=quoted, width=width, height=height)


__all__ = [
    "GroundingResult",
    "ask_about_screenshot",
    "ground_elements_by_text",
]
