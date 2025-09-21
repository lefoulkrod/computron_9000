"""Browser search/extraction tools.

Currently exposes:
    * ``extract_text`` - Extract visible text content from elements identified
      either by a CSS selector or (fallback) a visible text string.

Design goals:
    * Mirror error + logging patterns of other browser tools (``open_url``, ``click``)
    * Provide strongly typed, JSON-serializable Pydantic return models
    * Be resilient to transient Playwright failures (best-effort extraction)
"""

from __future__ import annotations

import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field

from tools.browser.core import get_browser
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import _element_css_selector  # internal helper for selector paths

logger = logging.getLogger(__name__)


class TextExtractionResult(BaseModel):
    """Single element text extraction result.

    Attributes:
        selector: Best-effort CSS selector (or synthetic indicator like ``text=...``)
            identifying the source element.
        text: Trimmed visible text content (possibly truncated).
    """

    selector: str = Field(..., max_length=200)
    text: str = Field(..., max_length=1000)


async def extract_text(target: str, limit: int = 1000) -> list[TextExtractionResult]:
    """Extract visible text by CSS selector or by visible text string.

    Args:
        target: Either a CSS selector (``div.hours p``) or a visible text
            snippet (``Business Hours``). Leading/trailing whitespace ignored.
        limit: Maximum number of characters to keep per element's text (default 1000).

    Returns:
        List of ``TextExtractionResult`` items (may be empty if nothing matched).

    Raises:
        BrowserToolError: If the browser/page cannot be accessed or if ``target``
            is empty.
    """
    clean_target = target.strip()
    if not clean_target:
        msg = "target must be a non-empty string"
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

    # First attempt: exact visible text match (mirrors click tool ordering)
    text_locator = None
    try:  # Attempt exact match first
        potential = page.get_by_text(clean_target, exact=True)
        if await potential.count() > 0:  # pragma: no branch - simple branch
            text_locator = potential.first
    except PlaywrightError:  # pragma: no cover - defensive
        text_locator = None

    if text_locator is not None:
        try:
            raw_text = await text_locator.inner_text()
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to read inner_text for exact text %s: %s", clean_target, exc)
        else:
            text_val = (raw_text or "").strip().replace("\n", " ")
            if text_val:
                # Attempt to compute a concrete CSS selector path for the matched element.
                css_selector = ""
                try:
                    # Some test doubles may not provide element handle semantics.
                    if hasattr(text_locator, "element_handle"):
                        handle = await text_locator.element_handle()  # type: ignore[attr-defined]
                        if handle is not None:  # pragma: no branch - simple guard
                            css_selector = await _element_css_selector(handle)
                except PlaywrightError:  # pragma: no cover - defensive
                    css_selector = ""
                # Fallback to synthetic text= marker if we could not compute.
                selector_value = css_selector or f"text={clean_target}"[:200]
                results.append(
                    TextExtractionResult(
                        selector=selector_value[:200],
                        text=text_val[:limit],
                    )
                )
                return results

    # Fallback: treat as CSS selector
    try:
        locator = page.locator(clean_target).first
        if await locator.count() == 0:
            # Final fallback: non-exact text search (substring / partial)
            try:
                substring_locator = page.get_by_text(clean_target, exact=False).first
                try:
                    await substring_locator.wait_for(timeout=2000)
                except PlaywrightTimeoutError:
                    return results
                raw_text = await substring_locator.inner_text()
                text_val = (raw_text or "").strip().replace("\n", " ")
                if text_val:
                    css_selector = ""
                    try:
                        if hasattr(substring_locator, "element_handle"):
                            handle = await substring_locator.element_handle()  # type: ignore[attr-defined]
                            if handle is not None:
                                css_selector = await _element_css_selector(handle)
                    except PlaywrightError:  # pragma: no cover - defensive
                        css_selector = ""
                    selector_value = css_selector or f"text~={clean_target}"[:200]
                    results.append(
                        TextExtractionResult(
                            selector=selector_value[:200],
                            text=text_val[:limit],
                        )
                    )
            except PlaywrightError as exc:  # pragma: no cover - defensive
                logger.debug("Substring text fallback failed for %s: %s", clean_target, exc)
            return results

        # We have at least one element for the CSS selector; gather all matches.
        # Re-query full set (not just .first) to count and iterate.
        full_locator = page.locator(clean_target)
        count = await full_locator.count()
        for idx in range(count):
            handle = full_locator.nth(idx)
            try:
                raw_text = await handle.inner_text()
            except PlaywrightError as exc:  # pragma: no cover - defensive per-element
                logger.debug("Failed inner_text for element %s at %s: %s", idx, clean_target, exc)
                continue
            text_val = (raw_text or "").strip().replace("\n", " ")
            if text_val:
                suffix = f":nth-of-type({idx + 1})" if count > 1 else ""
                sel_render = f"{clean_target}{suffix}"[:200]
                results.append(
                    TextExtractionResult(
                        selector=sel_render,
                        text=text_val[:limit],
                    )
                )
    except PlaywrightError as exc:  # pragma: no cover - selector failure
        logger.debug("Selector processing failed for %s: %s", clean_target, exc)

    return results


__all__ = ["TextExtractionResult", "extract_text"]
