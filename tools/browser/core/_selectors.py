"""Locator resolution utilities used by browser tools.

Provides ``_resolve_locator`` which resolves a caller-provided target string
into a Playwright ``Locator`` using strategies: exact visible text, selector
handle lookup (commonly a CSS selector), or substring text. The function
returns a ``_LocatorResolution`` dataclass with metadata about the chosen
strategy and matched elements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Locator,
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _LocatorResolution:
    """Resolution metadata for a resolved locator.

    Attributes:
        locator: Playwright ``Locator`` for the resolved elements.
        strategy: One of ``"text_exact"``, ``"css"``, or ``"text_substring"``.
        query: Original caller-supplied target string.
        match_count: Number of elements matched under the chosen strategy.
        resolved_selector: Canonical selector string used to perform the lookup.
    """

    locator: Locator
    strategy: Literal["text_exact", "css", "text_substring"]
    query: str
    match_count: int
    resolved_selector: str


async def _resolve_locator(
    page: Page,
    target: str,
    *,
    allow_substring_text: bool,
    require_single_match: bool,
    tool_name: str,
) -> _LocatorResolution | None:
    """Resolve ``target`` into a Playwright locator.

    Args:
        page: Active Playwright page.
        target: Text or selector handle supplied by the caller.
        allow_substring_text: Whether to fall back to substring text matches.
        require_single_match: Whether multiple matches should trigger an error.
        tool_name: Tool identifier used for ``BrowserToolError``.

    Returns:
        Locator resolution metadata, or ``None`` when nothing matched.

    Raises:
        BrowserToolError: On invalid input or ambiguity when ``require_single_match``
            is ``True``.
    """
    clean_target = target.strip()
    if not clean_target:
        msg = "target must be a non-empty string"
        raise BrowserToolError(msg, tool=tool_name)

    # 1) Exact visible text
    try:
        exact_locator = page.get_by_text(clean_target, exact=True)
        count = await exact_locator.count()
    except PlaywrightError as exc:
        logger.debug("Exact text lookup failed for %s: %s", clean_target, exc)
    else:
        if count > 0:
            if count > 1 and require_single_match:
                details = {
                    "strategy": "text_exact",
                    "matches": count,
                    "query": clean_target,
                }
                msg = (
                    f"Multiple elements match the exact text '{clean_target}'. Provide a more specific selector handle."
                )
                raise BrowserToolError(msg, tool=tool_name, details=details)
            locator = exact_locator.first
            return _LocatorResolution(
                locator=locator,
                strategy="text_exact",
                query=clean_target,
                match_count=count,
                resolved_selector=f"text={clean_target}",
            )

    # 2) Selector handle (commonly a CSS selector)
    try:
        css_locator = page.locator(clean_target)
        count = await css_locator.count()
    except PlaywrightError as exc:
        logger.debug("Selector handle lookup failed for %s: %s", clean_target, exc)
    else:
        if count > 0:
            if count > 1 and require_single_match:
                details = {
                    "strategy": "css",
                    "matches": count,
                    "query": clean_target,
                }
                msg = f"Selector handle '{clean_target}' matched multiple elements. Provide a more specific selector."
                raise BrowserToolError(msg, tool=tool_name, details=details)
            locator = css_locator.first if require_single_match else css_locator
            return _LocatorResolution(
                locator=locator,
                strategy="css",
                query=clean_target,
                match_count=count,
                resolved_selector=clean_target,
            )

    if not allow_substring_text:
        return None

    # 3) Substring text (best-effort)
    try:
        substring_locator = page.get_by_text(clean_target, exact=False)
        first_locator = substring_locator.first
        await first_locator.wait_for(timeout=2000)
        count = await substring_locator.count()
    except PlaywrightTimeoutError:
        return None
    except PlaywrightError as exc:
        logger.debug("Substring text lookup failed for %s: %s", clean_target, exc)
        return None

    if count == 0:
        return None

    if count > 1 and require_single_match:
        details = {
            "strategy": "text_substring",
            "matches": count,
            "query": clean_target,
        }
        msg = f"Multiple elements contain the text '{clean_target}'. Provide a more specific selector handle."
        raise BrowserToolError(msg, tool=tool_name, details=details)

    locator = substring_locator.first
    return _LocatorResolution(
        locator=locator,
        strategy="text_substring",
        query=clean_target,
        match_count=count,
        resolved_selector=f"text~={clean_target}",
    )


__all__ = [
    "_LocatorResolution",
    "_resolve_locator",
]
