"""Browser tools: tab-aware navigation (goto, new_tab, close_tab)."""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.events import emit_screenshot_after
from tools.browser.interactions import _format_result

logger = logging.getLogger(__name__)


@emit_screenshot_after
async def goto(url: str, tab: str | None = None) -> str:
    """Navigate a tab to ``url`` and return the page snapshot.

    With no tabs open, the first ``goto`` auto-creates the tab and
    navigates it.  With one tab open, ``tab`` may be omitted.  With
    multiple tabs open, ``tab`` is required — pass the ID shown in the
    snapshot header (e.g. ``tab="3"``).

    Two concurrent ``goto`` calls on the same tab error loudly — open
    pages in parallel with ``new_tab(url)`` instead.

    Args:
        url: The URL to navigate to.
        tab: Stable tab ID to navigate.  Omit when only one tab is
            open or no tabs exist (a fresh one will be created).

    Returns:
        Annotated page snapshot of the navigated tab.
    """
    try:
        browser = await browser_core.get_browser()
        if tab is None and not browser.open_tabs():
            page = await browser.new_page()
        else:
            try:
                page = browser.resolve_tab(tab)
            except ValueError as exc:
                raise BrowserToolError(str(exc), tool="goto") from exc
        result = await browser.navigate(url, page=page)
        return await _format_result(result, tool_name="goto")
    except BrowserToolError:
        raise
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("goto failed for %s", url)
        raise BrowserToolError(str(exc), tool="goto") from exc


@emit_screenshot_after
async def new_tab(url: str) -> str:
    """Open a new tab at ``url`` and return its snapshot.

    Use this when you want to keep the current page intact and view
    something else in addition — e.g. opening a search result without
    losing the listing, or fetching several pages in parallel.

    Args:
        url: The URL the new tab should navigate to.

    Returns:
        Annotated page snapshot of the new tab.  The header carries the
        new tab's ID (``tab=N``) — use that ID on subsequent tools to
        act on this tab.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.new_page()
        result = await browser.navigate(url, page=page)
        return await _format_result(result, tool_name="new_tab")
    except BrowserToolError:
        raise
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("new_tab failed for %s", url)
        raise BrowserToolError(str(exc), tool="new_tab") from exc


async def close_tab(tab: str | None = None) -> str:
    """Close a tab and free its resources.

    With one tab open, ``tab`` may be omitted.  With multiple tabs,
    pass the ID of the tab to close.  Closing a tab does not free its
    ID — stale references to a closed tab fail loud rather than
    silently landing on a different tab.

    Args:
        tab: Stable tab ID to close.  Omit when only one tab is open.

    Returns:
        Confirmation line naming the closed tab.  Current open-tab
        state is reflected in the next snapshot header — this tool
        does not list it because parallel ``close_tab`` calls would
        produce inconsistent listings (each call's snapshot is taken
        at its own completion time).
    """
    try:
        browser = await browser_core.get_browser()
        try:
            page = browser.resolve_tab(tab)
        except ValueError as exc:
            raise BrowserToolError(str(exc), tool="close_tab") from exc
        closed_id = browser.tab_id_of(page)
        await page.close()
        return f"Closed tab={closed_id}."
    except BrowserToolError:
        raise
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("close_tab failed for %s", tab)
        raise BrowserToolError(str(exc), tool="close_tab") from exc


__all__ = ["close_tab", "goto", "new_tab"]
