"""String formatting for browser tool results.

Converts internal PageView and InteractionResult data into plain-text
strings for LLM consumption.  Keeps all formatting logic in one place.
"""

from __future__ import annotations

from typing import Any


def format_page_view(
    *,
    title: str,
    url: str,
    status_code: int | None,
    viewport: dict[str, int] | None,
    content: str,
    truncated: bool,
    downloaded_file: Any | None = None,
) -> str:
    """Format a page view as a plain-text string for the LLM.

    Args:
        title: Page title.
        url: Final URL after redirects.
        status_code: HTTP status code or None.
        viewport: Viewport/scroll state dict.
        content: Annotated page content.
        truncated: Whether content was truncated.
        downloaded_file: Optional DownloadInfo from file detection.

    Returns:
        Formatted string with header and content.
    """
    if downloaded_file is not None:
        from tools.browser.core._file_detection import format_download_message

        return format_download_message(downloaded_file)

    status = status_code if status_code is not None else ""
    trunc = " | truncated" if truncated else ""

    header = f"[Page: {title} | {url} | {status}]"
    if viewport is None:
        vp_line = "[Viewport: unavailable]"
    else:
        scroll_top = viewport.get("scroll_top", 0)
        vh = viewport.get("viewport_height", 0)
        doc_h = viewport.get("document_height", 0)
        vp_line = f"[Viewport: {scroll_top}-{scroll_top + vh} of {doc_h}px{trunc}]"

    return f"{header}\n{vp_line}\n\n{content}"


def format_interaction_result(
    *,
    reason: str,
    page_changed: bool,
    page_view_str: str | None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Format an interaction result as a plain-text string for the LLM.

    Args:
        reason: Classification of the change.
        page_changed: Whether the page changed.
        page_view_str: Formatted page view string (from format_page_view).
        extras: Additional metadata (scroll state, etc.).

    Returns:
        Formatted string with action header and page view.
    """
    changed = "yes" if page_changed else "no"
    header = f"[Action: {reason} | page_changed: {changed}]"

    if page_view_str is None:
        return header

    return f"{header}\n{page_view_str}"
