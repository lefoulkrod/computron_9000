"""Browser tool: open a URL and return a lightweight page snapshot.

Implementation delegates snapshot extraction to shared internal helper
``_build_page_snapshot`` located in ``tools.browser.core.snapshot`` so
other tools can re-use consistent snapshot semantics.
"""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import (
    Element,
    PageSnapshot,
    _build_page_snapshot,
    _collect_anchors,
    _collect_clickables,
)

logger = logging.getLogger(__name__)


async def open_url(url: str) -> PageSnapshot:
    """Open a URL in the shared browser and return a page snapshot.

    The returned snapshot's elements list includes the first 20 anchors, all forms and iframes.

    Args:
        url: The URL to open (http/https).

    Returns:
        PageSnapshot: Pydantic model with title, url, snippet, elements, status_code.

    Raises:
        BrowserToolError: If navigation or extraction fails.
    """
    try:
        # Access via module attribute so tests can monkeypatch tools.browser.core.get_browser
        browser = await browser_core.get_browser()
        page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        return await _build_page_snapshot(page, response)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc


async def current_page() -> PageSnapshot:
    """Return a snapshot of the currently open page without creating a new one.

    The returned snapshot's elements list includes the first 20 anchors, all forms and iframes.

    Returns:
        PageSnapshot: Structured snapshot of the active page (title, url,
        snippet, elements, status_code).

    Raises:
        BrowserToolError: If there is no open page or if snapshot extraction
            fails for any reason.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.current_page()  # will raise RuntimeError if none
    except RuntimeError as exc:
        logger.debug("No current page available: %s", exc)
        msg = "No open page to snapshot"
        raise BrowserToolError(msg, tool="current_page") from exc
    except Exception as exc:  # pragma: no cover - defensive broad guard
        logger.exception("Failed to access browser for current page snapshot")
        msg = "Unable to access browser pages"
        raise BrowserToolError(msg, tool="current_page") from exc

    try:
        return await _build_page_snapshot(page, None)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to build snapshot of current page")
        msg = "Failed to snapshot current page"
        raise BrowserToolError(msg, tool="current_page") from exc


async def list_clickable_elements(
    after: str | None = None, limit: int = 20, contains: str | None = None
) -> list[Element]:
    """List clickable elements (anchors plus heuristic non-semantic clickables).

    The result merges native anchors (<a>) and additional interactive elements
    discovered by the internal ``_collect_clickables`` helper (e.g. div/span with
    onclick, role="button", etc.). Ordering preserves document order within each
    category and mirrors snapshot extraction ordering (anchors appear after any
    earlier button/clickable categories, but this tool only returns anchors and
    heuristic clickables).

    Args:
        after: Optional selector string acting as a cursor. If provided, results
            start strictly after the first element whose ``selector`` equals
            this value. If not found, iteration starts from the beginning.
        limit: Maximum number of elements to return after filtering/paging.
        contains: Optional case-insensitive substring filter applied to the
            element's visible text OR (for anchors) its href.

    Returns:
        list[Element]: Sliced list of clickable ``Element`` models.

    Raises:
        BrowserToolError: If there is no active page or extraction fails.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.current_page()
    except RuntimeError as exc:
        logger.debug("No current page available for list_clickable_elements: %s", exc)
        raise BrowserToolError("No open page to list clickable elements", tool="list_clickable_elements") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to access browser for list_clickable_elements")
        raise BrowserToolError("Unable to access browser pages", tool="list_clickable_elements") from exc

    try:
        # Collect both sets; anchors first for backward-ish ordering in pagination.
        anchors = await _collect_anchors(page)
        clickables = await _collect_clickables(page, limit=None)
        combined: list[Element] = []
        combined.extend(anchors)
        combined.extend(clickables)
    except Exception as exc:  # pragma: no cover - wrap
        logger.exception("Failed to collect clickable elements")
        raise BrowserToolError("Failed to collect clickable elements", tool="list_clickable_elements") from exc

    if contains:
        needle = contains.lower()

        def matches(e: Element) -> bool:
            txt = (e.text or "").lower()
            href = (e.href or "").lower()
            return needle in txt or needle in href

        combined = [e for e in combined if matches(e)]

    start_idx = 0
    if after:
        for idx, el in enumerate(combined):
            if el.selector == after:
                start_idx = idx + 1
                break
    sliced = combined[start_idx : start_idx + max(0, int(limit or 0))]
    return sliced
