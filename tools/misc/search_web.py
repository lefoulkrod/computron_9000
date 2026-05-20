"""Search the web via DuckDuckGo and return plain-text results."""

from __future__ import annotations

import asyncio
import logging

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_MAX_RESULTS = 10
_RESULT_BUDGET = 8_000


def _run_search(query: str, max_results: int) -> list[dict[str, str]]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web and return text results without opening a browser.

    Use this to look up facts, current events, or any information available
    on the web.  Returns titles, URLs, and snippets — no screenshots or visual
    parsing required.

    Args:
        query: The search query.
        max_results: Number of results to return (1–10, default 5).

    Returns:
        Formatted string listing numbered results, each with title, URL,
        and a text snippet.  Returns a plain message when no results are found.

    Raises:
        RuntimeError: If the search request fails.
    """
    max_results = max(1, min(max_results, _MAX_RESULTS))

    try:
        raw: list[dict[str, str]] = await asyncio.to_thread(
            _run_search, query, max_results
        )
    except Exception as exc:
        logger.exception("DuckDuckGo search failed for query %r", query)
        raise RuntimeError(f"Search failed: {exc}") from exc

    if not raw:
        return f'No results found for "{query}".'

    lines: list[str] = [f'Search: "{query}" — {len(raw)} result(s)\n']
    for i, result in enumerate(raw, 1):
        lines.append(f"{i}. {result.get('title', '(no title)')}")
        lines.append(f"   {result.get('href', '')}")
        snippet = result.get("body", "").strip()
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    output = "\n".join(lines)
    if len(output) > _RESULT_BUDGET:
        output = output[:_RESULT_BUDGET] + "\n[truncated]"
    return output


__all__ = ["search_web"]
