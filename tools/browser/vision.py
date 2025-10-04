"""Vision-enabled browser tools built on top of the shared Ollama model."""

# ruff: noqa: I001

from __future__ import annotations

import base64
import json
import logging
from typing import Any, cast

from ollama import AsyncClient, Image
from playwright.async_api import Error as PlaywrightError, Page
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import load_config
from models.model_configs import get_model_by_name
from tools.browser.core import get_browser
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import _build_page_snapshot

logger = logging.getLogger(__name__)

_SCREENSHOT_TOOL_NAME = "ask_about_screenshot"
_GROUNDING_TOOL_NAME = "ground_elements_by_text"
_PROMPT_TEMPLATE = """You are a UI grounding assistant.
Given this screenshot, return bounding boxes for all elements that match the description {text_json}.
Format the output strictly as JSON: [{{"element": "...", "text": "...", "bbox": [x,y,width,height]}}]"""


class GroundingResult(BaseModel):
    """Result for a grounded UI element.

    Fields:
        text: visible text the model matched
        bbox: (x, y, width, height) in viewport pixel coordinates
        selector: best-effort selector handle resolved from the page at the bbox center
    """

    text: str = Field(..., max_length=200)
    bbox: tuple[int, int, int, int]
    selector: str | None = None

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
        selector: When ``mode == "selector"``, a selector string (selector handle)
            targeting the element to capture.

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

    Args:
        description: The descriptive text to locate on the page.

    Returns:
        list[GroundingResult]: Bounding boxes with element metadata from the vision model.

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
        await _build_page_snapshot(page, None)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to build snapshot before grounding request")
        msg = "Failed to snapshot current page."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

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

    encoded_image = _encode_image(screenshot_bytes)

    client, model = _make_vision_client(tool_name=_GROUNDING_TOOL_NAME)
    prompt = _render_prompt(clean_text)

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
    logger.debug("Raw grounding response: %s", raw_response)

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
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.exception("Vision model returned invalid JSON for grounding request")
        msg = "Vision model returned invalid JSON."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

    if not isinstance(parsed, list):
        msg = "Vision model response must be a list of bounding boxes."
        raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME)

    results: list[GroundingResult] = []
    for entry in parsed:
        try:
            # Expect entries like {"element": "...", "text": "...", "bbox": [x,y,w,h]}
            validated = GroundingResult.model_validate(
                {
                    "text": entry.get("text"),
                    "bbox": tuple(entry.get("bbox", [])),
                    "selector": None,
                },
                strict=False,
            )
        except ValidationError as exc:
            logger.exception("Vision model produced an invalid grounding entry: %s", entry)
            msg = "Vision model returned invalid bounding box entries."
            raise BrowserToolError(msg, tool=_GROUNDING_TOOL_NAME) from exc

        # Resolve selector from bbox center using document.elementFromPoint via page.evaluate
        try:
            x, y, w, h = validated.bbox
            cx = int(x + w / 2)
            cy = int(y + h / 2)

            # Call into the page to compute a selector handle for the element at the center.
            # _best_selector is a helper that lives on the Python side; we call document.elementFromPoint
            # to obtain an element's unique identifier then pass it into _best_selector via a temporary
            # element attribute. This keeps selector resolution robust in tests by using the page JS context.
            handle = None
            try:
                # Run an in-page helper to build a best-effort selector for the element
                # at the center point. This prefers id, data-selector, named attributes,
                # unique class selectors, and falls back to a tag > ... > nth-child path.
                js = """([x, y]) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return null;
  if (el.id) return '#' + el.id;
  const ds = el.getAttribute('data-selector');
  if (ds) return ds;
  const attrs = ['name','aria-label','alt','title','role'];
  for (const a of attrs) {
    const v = el.getAttribute(a);
    if (v) return el.tagName.toLowerCase() + '[' + a + '"' + v + '"' + ']';
  }
  if (el.classList && el.classList.length) {
    const classes = Array.from(el.classList).slice(0,3);
    const cls = el.tagName.toLowerCase() + '.' + classes.join('.');
    try { if (document.querySelectorAll(cls).length === 1) return cls; } catch(e) {}
  }
  function pathFor(elm) {
    const parts = [];
    while (elm && elm.nodeType === Node.ELEMENT_NODE && elm.tagName.toLowerCase() !== 'html') {
      let part = elm.tagName.toLowerCase();
      if (elm.id) { parts.unshift(part + '#' + elm.id); break; }
      if (elm.classList && elm.classList.length) { part += '.' + Array.from(elm.classList).slice(0,2).join('.'); }
      const parent = elm.parentNode;
      if (!parent) { parts.unshift(part); break; }
      const idx = Array.prototype.indexOf.call(parent.children, elm) + 1;
      part += ':nth-child(' + idx + ')';
      parts.unshift(part); elm = parent;
    }
    return parts.join(' > ');
  }
  try { return pathFor(el); } catch (e) { return null; }
}"""
                selector_candidate = await page.evaluate(js, [cx, cy])
                logger.debug(
                    "Tried bbox candidate %s -> center %s,%s selector=%s",
                    (x, y, w, h),
                    cx,
                    cy,
                    selector_candidate,
                )
                if selector_candidate:
                    handle = str(selector_candidate)
            except PlaywrightError:
                logger.exception(
                    "Selector resolution via elementFromPoint failed for bbox center %s,%s",
                    cx,
                    cy,
                )
            except Exception:
                logger.exception(
                    "Selector resolution via elementFromPoint failed for bbox center %s,%s",
                    cx,
                    cy,
                )

            validated.selector = handle
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


def _render_prompt(visible_text: str) -> str:
    """Build the grounding prompt with JSON-compliant quoting."""
    quoted = json.dumps(visible_text)
    return _PROMPT_TEMPLATE.format(text_json=quoted)


__all__ = [
    "GroundingResult",
    "ask_about_screenshot",
    "ground_elements_by_text",
]
