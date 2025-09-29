"""Browser search and text extraction utilities.

This module provides the ``extract_text`` helper which extracts visible text
from elements identified by a selector handle or by visible text. Results are
returned as Pydantic models for safe serialization.
"""

from __future__ import annotations

import logging

from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

from tools.browser.core import get_browser
from tools.browser.core._selectors import _LocatorResolution, _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import _element_css_selector  # internal helper for selector paths

logger = logging.getLogger(__name__)


class TextExtractionResult(BaseModel):
    """Single element text extraction result.

    Attributes:
        selector: Best-effort selector handle (or synthetic indicator like ``"text=..."``)
            identifying the source element.
        text: Trimmed visible text content (possibly truncated).
    """

    selector: str = Field(..., max_length=200)
    text: str = Field(..., max_length=1000)


async def extract_text(selector: str, limit: int = 1000) -> list[TextExtractionResult]:
    """Extract visible text by selector handle or by visible text string.

    Args:
        selector: Either a selector handle (for example ``div.hours p``) or a visible text
            snippet (``Business Hours``). Leading/trailing whitespace ignored. Prefer the
            `selector` field returned in page snapshots; fall back to visible text when no
            selector is available.
        limit: Maximum number of characters to keep per element's text (default 1000).

    Returns:
        List of ``TextExtractionResult`` items (may be empty if nothing matched).

    Raises:
        BrowserToolError: If the browser/page cannot be accessed or if ``target``
            is empty.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string"
        raise BrowserToolError(msg, tool="extract_text")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for extract_text")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="extract_text") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before attempting to extract text."
        raise BrowserToolError(msg, tool="extract_text")

    results: list[TextExtractionResult] = []

    try:
        resolution: _LocatorResolution | None = await _resolve_locator(
            page,
            clean_selector,
            allow_substring_text=True,
            require_single_match=False,
            tool_name="extract_text",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for extract_text selector %s", clean_selector)
        msg = "Unable to resolve locator for text extraction"
        raise BrowserToolError(msg, tool="extract_text") from exc

    if resolution is None:
        return results

    if resolution.strategy == "css":
        locator = resolution.locator
        try:
            count = resolution.match_count
        except AttributeError:  # pragma: no cover - defensive
            count = await locator.count()
        for idx in range(count):
            handle = locator.nth(idx)
            try:
                raw_text = await handle.inner_text()
            except PlaywrightError as exc:  # pragma: no cover - defensive per-element
                logger.debug(
                    "Failed inner_text for element %s at %s: %s",
                    idx,
                    clean_selector,
                    exc,
                )
                continue
            text_val = (raw_text or "").strip().replace("\n", " ")
            if text_val:
                suffix = f":nth-of-type({idx + 1})" if count > 1 else ""
                base_selector = resolution.resolved_selector
                sel_render = f"{base_selector}{suffix}"[:200]
                results.append(
                    TextExtractionResult(
                        selector=sel_render,
                        text=text_val[:limit],
                    )
                )
        return results

    locator = resolution.locator
    try:
        raw_text = await locator.inner_text()
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read inner_text for text %s: %s", clean_selector, exc)
        return results

    text_val = (raw_text or "").strip().replace("\n", " ")
    if not text_val:
        return results

    css_selector = ""
    try:
        if hasattr(locator, "element_handle"):
            element_handle = await locator.element_handle()
            if element_handle is not None:
                css_selector = await _element_css_selector(element_handle)
    except PlaywrightError:  # pragma: no cover - defensive
        css_selector = ""

    selector_value = css_selector or resolution.resolved_selector
    results.append(
        TextExtractionResult(
            selector=selector_value[:200],
            text=text_val[:limit],
        )
    )
    return results


__all__ = ["TextExtractionResult", "extract_text"]
