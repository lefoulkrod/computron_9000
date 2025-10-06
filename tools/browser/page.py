"""Browser tool: open a URL and return a lightweight page snapshot.

Implementation delegates snapshot extraction to shared internal helper
``_build_page_snapshot`` located in ``tools.browser.core.snapshot`` so
other tools can re-use consistent snapshot semantics.
"""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import Element, PageSnapshot, _build_page_snapshot, _collect_anchors

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


async def list_anchors(after: str | None = None, limit: int = 20, contains: str | None = None) -> list[Element]:
    """List anchor elements on the active page with optional paging and filtering.

    Args:
        after: Optional selector string indicating the last-seen element. If
            provided, results start strictly after the first element whose
            ``selector`` equals this value. If the selector is not found the
            function will start from the beginning and return results normally.
        limit: Maximum number of anchors to return (sliced after filtering/paging).
        contains: Optional substring to filter anchors by visible text or href
            (case-insensitive).

    Returns:
        list[Element]: The selected slice of anchor Element models.

    Raises:
        BrowserToolError: If there is no active page to inspect or snapshot
            extraction fails.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.current_page()
    except RuntimeError as exc:
        logger.debug("No current page available for list_anchors: %s", exc)
        raise BrowserToolError("No open page to list anchors", tool="list_anchors") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to access browser for list_anchors")
        raise BrowserToolError("Unable to access browser pages", tool="list_anchors") from exc

    try:
        anchors = await _collect_anchors(page)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to collect anchors for list_anchors")
        raise BrowserToolError("Failed to collect anchors", tool="list_anchors") from exc

    # Optional case-insensitive substring filtering against text and href
    if contains:
        needle = contains.lower()

        def matches(e: Element) -> bool:
            txt = (e.text or "").lower()
            href = (e.href or "").lower()
            return needle in txt or needle in href

        anchors = [a for a in anchors if matches(a)]

    # Cursor-based paging using selector equality. If `after` is provided and
    # matches an element selector, start after that element. If not found we
    # start from the beginning (documented behavior).
    start_idx = 0
    if after:
        for idx, el in enumerate(anchors):
            if el.selector == after:
                start_idx = idx + 1
                break

    sliced = anchors[start_idx : start_idx + max(0, int(limit or 0))]
    return sliced
