"""Read the current page as clean text content (markdown)."""

from __future__ import annotations

import logging

from playwright.async_api import Error as PlaywrightError

from tools.browser.core import get_active_view
from tools.browser.core._formatting import format_page_view
from tools.browser.core._html import html_to_markdown
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)

_READ_BUDGET = 20_000
_QUERY_CONTEXT_LINES = 1

# JS to find the best content root and return its outerHTML.
# Prefers <article>, then <main>, then falls back to <body>.
_CONTENT_ROOT_JS = """
() => {
  const article = document.querySelector('article');
  if (article) return article.outerHTML;
  const main = document.querySelector('main');
  if (main) return main.outerHTML;
  return document.body.outerHTML;
}
"""


def _filter_by_query(
    content: str, query: str, page_number: int = 1
) -> tuple[str, bool]:
    """Filter markdown content to lines matching *query* with context.

    Returns a ``(text, truncated)`` tuple.  *text* contains matching lines
    with ``_QUERY_CONTEXT_LINES`` of surrounding context, grouped by
    proximity and separated by ``---``.  *page_number* selects which
    page of results to return (1-indexed).
    """
    query_lower = query.lower()
    lines = content.split("\n")

    matched_indices: set[int] = set()
    for i, line in enumerate(lines):
        if query_lower in line.lower():
            lo = max(0, i - _QUERY_CONTEXT_LINES)
            hi = min(len(lines), i + _QUERY_CONTEXT_LINES + 1)
            matched_indices.update(range(lo, hi))

    if not matched_indices:
        return "", False

    # Group consecutive line indices
    sorted_indices = sorted(matched_indices)
    groups: list[list[int]] = []
    current: list[int] = [sorted_indices[0]]
    for idx in sorted_indices[1:]:
        if idx > current[-1] + 1:
            groups.append(current)
            current = [idx]
        else:
            current.append(idx)
    groups.append(current)

    # Build all group texts
    group_texts: list[str] = []
    for group in groups:
        text = "\n".join(lines[j] for j in group).strip()
        if text:
            group_texts.append(text)

    # Paginate groups into pages that fit within the budget
    header = (
        f'[Filtered for "{query}" — {len(group_texts)} match(es) '
        f"from {len(content):,} chars]\n"
    )
    header_len = len(header)

    # Walk through groups, assigning them to pages
    current_page = 1
    page_parts: list[str] = []
    page_total = header_len
    separator_len = 4  # len("\n---\n")

    for text in group_texts:
        cost = len(text) + separator_len
        if page_parts and page_total + cost > _READ_BUDGET:
            # This group doesn't fit — start a new page
            if current_page == page_number:
                # We've filled the requested page, remaining = truncated
                return header + "\n---\n".join(page_parts), True
            current_page += 1
            page_parts = []
            page_total = header_len
        page_parts.append(text)
        page_total += cost

    # We've assigned all groups
    if current_page == page_number:
        return header + "\n---\n".join(page_parts), False
    # Requested page is past the end
    return "", False


async def read_page(
    page_number: int = 1,
    query: str | None = None,
) -> str:
    """Read the current page as clean markdown text.

    Use this when you need to READ: articles, docs, search results, any text
    content.  Returns markdown with headings, links, and lists — no
    interactive element annotations.  For finding clickable elements, use
    ``browse_page()`` instead.

    Content is paginated.  If the header shows ``truncated``, call
    ``read_page(page_number=2)`` for the next chunk.

    Args:
        page_number: Which chunk to return (1-indexed, default 1).
            Increment when the header shows ``truncated``.
        query: Filter to lines matching this text (case-insensitive).
            Returns matching lines with context, grouped by ``---``.
            Example: ``read_page(query="pricing")`` to find pricing info
            on a long page without reading everything.

    Returns:
        Formatted string with page header, viewport info, and markdown content.

    Raises:
        BrowserToolError: If there is no open page.
    """
    if page_number < 1:
        raise BrowserToolError(
            "page_number must be 1 or greater", tool="read_page"
        )

    _, view = await get_active_view("read_page")

    try:
        raw_html: str = await view.frame.evaluate(_CONTENT_ROOT_JS)
        full_content = html_to_markdown(raw_html)

        if query:
            # Filter mode — return only matching snippets
            content, truncated = _filter_by_query(
                full_content, query, page_number
            )
            if not content:
                content = (
                    f'No matches for "{query}" on this page '
                    f"({len(full_content):,} chars)."
                )
                truncated = False
        else:
            # Pagination mode — slice to the requested page
            start = (page_number - 1) * _READ_BUDGET
            end = start + _READ_BUDGET
            content = full_content[start:end]
            truncated = end < len(full_content)

            if not content and page_number > 1:
                raise BrowserToolError(
                    f"page_number {page_number} is past the end of the content",
                    tool="read_page",
                )

        # Get viewport info
        viewport_data: dict[str, int] = await view.frame.evaluate(
            """() => ({
                scroll_top: Math.floor(window.scrollY),
                viewport_height: Math.floor(window.innerHeight),
                viewport_width: Math.floor(window.innerWidth),
                document_height: Math.floor(document.scrollingElement
                    ? document.scrollingElement.scrollHeight
                    : document.body.scrollHeight)
            })"""
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to read page content")
        raise BrowserToolError(
            "Failed to read page content", tool="read_page"
        ) from exc

    return format_page_view(
        title=view.title,
        url=view.url,
        status_code=None,
        viewport=viewport_data,
        content=content,
        truncated=truncated,
    )


__all__ = ["read_page"]
