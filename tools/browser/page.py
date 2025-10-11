"""Browser tool: open a URL and return a lightweight page snapshot.

Implementation delegates snapshot extraction to shared internal helper
``_build_page_snapshot`` located in ``tools.browser.core.snapshot`` so
other tools can re-use consistent snapshot semantics.
"""

from __future__ import annotations

import logging

from playwright.async_api import Error as PlaywrightError

import tools.browser.core as browser_core
from tools.browser.core._selectors import _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.selectors import SelectorRegistry
from tools.browser.core.snapshot import (
    Element,
    PageSnapshot,
    _build_page_snapshot,
    _collect_anchors,
    _collect_buttons,
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


_SCOPE_ANCESTOR_MAX_DEPTH = 5


async def list_clickable_elements(
    after: str | None = None,
    limit: int = 20,
    contains: str | None = None,
    scope: str | None = None,
) -> list[Element]:
    """List clickable elements (buttons, anchors, and heuristic clickables).

    The result merges native buttons, anchors (<a>), and additional interactive elements
    (e.g. div/span with onclick, role="link", etc.).

    Args:
        after: Optional selector string acting as a cursor. If provided, results
            start strictly after the first element whose ``selector`` equals
            this value. If not found, iteration starts from the beginning.
        limit: Maximum number of elements to return after filtering/paging.
        contains: Optional case-insensitive substring filter applied to the
            element's visible text OR (for anchors) its href.

    Args:
        after: Optional selector string cursor (results begin strictly after this selector).
        limit: Maximum number of elements to return after filtering/paging.
        contains: Optional case-insensitive substring filter applied to visible text or href.
        scope: Optional parent container scoping the search. Accepts either exact visible text
            or a selector handle.

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
        # Resolve optional scope container
        root_locator = None
        if scope is not None:
            query = scope.strip()
            if not query:
                raise BrowserToolError("scope must be a non-empty string", tool="list_clickable_elements")

            # Use shared resolver: exact text, then CSS; no substring; require single.
            resolution = await _resolve_locator(
                page,
                query,
                allow_substring_text=False,
                require_single_match=True,
                tool_name="list_clickable_elements",
            )
            if resolution is None:
                raise BrowserToolError("scope container not found", tool="list_clickable_elements")
            candidate = resolution.locator

            # Ancestor climb: consider node plus up to N ancestors; choose the first that appears to contain clickables
            current = candidate
            chosen = None
            depth = 0
            while depth <= _SCOPE_ANCESTOR_MAX_DEPTH:
                try:
                    btn_count = await current.locator(":scope button, :scope [role=button]").count()
                    a_count = await current.locator(":scope a").count()
                    # Heuristic clickable selectors (same set as _collect_clickables)
                    heur_scoped = (
                        ":scope div[onclick], :scope span[onclick], :scope li[onclick], "
                        ":scope [role='link'], :scope [tabindex], :scope [data-clickable]"
                    )
                    heur_count = await current.locator(heur_scoped).count()
                except PlaywrightError:  # pragma: no cover - defensive
                    btn_count = a_count = heur_count = 0

                if (btn_count + a_count + heur_count) > 0:
                    chosen = current
                    break
                # Move to parent element if possible
                parent = current.locator("xpath=..")
                try:
                    if await parent.count() == 0:
                        break
                except PlaywrightError:  # pragma: no cover - defensive
                    break
                current = parent.first
                depth += 1
            root_locator = chosen if chosen is not None else candidate

        # Collect buttons, anchors, then heuristic clickables. Use one registry for uniqueness.
        registry = SelectorRegistry(page)
        buttons = await _collect_buttons(page, registry, root=root_locator)
        anchors = await _collect_anchors(page, registry, root=root_locator)
        clickables = await _collect_clickables(page, registry, limit=None, root=root_locator)
        combined: list[Element] = []
        combined.extend(buttons)
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
