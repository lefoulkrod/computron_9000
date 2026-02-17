"""Locator resolution utilities used by browser tools.

Provides ``_resolve_locator`` which resolves a caller-provided target string
into a Playwright ``Locator`` using strategies: role:name (from annotated
snapshots), CSS selector handle, exact visible text, or substring text.
The function returns a ``_LocatorResolution`` dataclass with metadata about
the chosen strategy and matched elements.
"""

from __future__ import annotations

import logging
import re
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

# Valid ARIA roles accepted in the ``role:name`` selector format.
_VALID_ROLES = frozenset({
    "alert", "alertdialog", "button", "cell", "checkbox", "columnheader",
    "combobox", "dialog", "grid", "gridcell", "heading", "img", "link",
    "list", "listbox", "listitem", "menu", "menubar", "menuitem",
    "menuitemcheckbox", "menuitemradio", "navigation", "option",
    "progressbar", "radio", "row", "rowheader", "searchbox", "slider",
    "spinbutton", "status", "switch", "tab", "tabpanel", "textbox",
    "tooltip", "tree", "treeitem",
})

# Pattern to detect optional [N] index suffix: ``button:Add to Cart[1]``
_INDEX_SUFFIX_RE = re.compile(r"^(.+)\[(\d+)\]$")


def _parse_role_name(target: str) -> tuple[str, str | None, int | None] | None:
    """Parse ``role:name``, ``role:name[N]``, or bare ``role`` selector format.

    Returns ``(role, name, index)`` or ``None`` if the string does not match
    the expected format.  ``name`` is ``None`` for bare role selectors (e.g.
    ``"combobox"`` or ``"combobox:"``).  ``index`` is ``None`` when no ``[N]``
    suffix is present.
    """
    colon_idx = target.find(":")
    if colon_idx <= 0:
        # No colon — check if the entire string is a valid bare role.
        role = target.strip().lower()
        if role in _VALID_ROLES:
            return (role, None, None)
        return None
    role = target[:colon_idx].strip().lower()
    if role not in _VALID_ROLES:
        return None
    raw_name = target[colon_idx + 1:].strip()
    if not raw_name:
        # Trailing colon with no name (e.g. "combobox:") — bare role match.
        return (role, None, None)

    # Check for [N] index suffix
    index: int | None = None
    m = _INDEX_SUFFIX_RE.match(raw_name)
    if m:
        raw_name = m.group(1).strip()
        index = int(m.group(2))

    return (role, raw_name, index)


async def _filter_to_viewport(
    locator: Locator,
    count: int,
    page: Page,
) -> tuple[Locator | None, int]:
    """Filter a multi-match locator to elements visible in the viewport.

    Returns ``(locator, visible_count)``.  If exactly one element is visible
    in the viewport, returns a locator pointing to that specific element.
    If none or multiple are visible, returns ``(None, visible_count)``.
    """
    viewport_size = page.viewport_size or {"width": 1280, "height": 800}
    vh = viewport_size["height"]

    visible_indices: list[int] = []
    # Cap iteration to avoid excessive round-trips on pages with hundreds of matches
    check_limit = min(count, 50)
    for i in range(check_limit):
        nth = locator.nth(i)
        try:
            box = await nth.bounding_box(timeout=500)
        except (PlaywrightError, PlaywrightTimeoutError):
            continue
        if box and box["width"] > 0 and box["height"] > 0 and box["y"] < vh and box["y"] + box["height"] > 0:
            try:
                if await nth.is_visible():
                    visible_indices.append(i)
            except (PlaywrightError, PlaywrightTimeoutError):
                continue

    if len(visible_indices) == 1:
        return locator.nth(visible_indices[0]), 1
    return None, len(visible_indices)


@dataclass(slots=True)
class _LocatorResolution:
    """Resolution metadata for a resolved locator.

    Attributes:
        locator: Playwright ``Locator`` for the resolved elements.
        strategy: Resolution strategy that succeeded.
        query: Original caller-supplied target string.
        match_count: Number of elements matched under the chosen strategy.
        resolved_selector: Canonical selector string used to perform the lookup.
    """

    locator: Locator
    strategy: Literal["role_name", "text_exact", "css", "text_substring"]
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

    Strategies are tried in order:

    0. **role:name** — ``"button:Add to Cart"`` is parsed and resolved via
       ``page.get_by_role()``.  When multiple elements share the same
       role:name, a viewport-visibility filter narrows to the one the agent
       can see.  An optional ``[N]`` index suffix (e.g.
       ``button:Add to Cart[1]``) selects a specific match.
    1. **CSS / Playwright selector** — tried first for generated selectors.
    2. **Exact visible text** — for plain-text targets like ``"Sign in"``.
    3. **Substring text** — only if ``allow_substring_text`` is ``True``.

    Args:
        page: Active Playwright page.
        target: Text, ``role:name`` pair, or selector handle.
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

    # 0) role:name selector (from annotated snapshot output).
    parsed = _parse_role_name(clean_target)
    if parsed is not None:
        role, name, index = parsed
        # Build the role locator — with or without name filter.
        try:
            if name is not None:
                # If the name was truncated in the snapshot (ends with ...),
                # use substring matching so "KVIDIO Bluetooth Headphones..."
                # still works.
                exact = not name.endswith("...")
                search_name = name.rstrip(".") if not exact else name
                role_locator = page.get_by_role(role, name=search_name, exact=exact)  # type: ignore[arg-type]
            else:
                # Bare role (e.g. "combobox" or "combobox:") — match any
                # element with this role regardless of accessible name.
                role_locator = page.get_by_role(role)  # type: ignore[arg-type]
            count = await role_locator.count()
            # When exact match finds nothing, probe with substring matching
            # to give the agent actionable feedback.  The DOM walker reports
            # visible text (innerText) but Playwright matches against the
            # full ARIA accessible name which can include visually-hidden
            # text (e.g. Amazon's "Proceed to checkout" input whose
            # accessible name is "Proceed to checkout Check out Amazon
            # Cart").  Rather than silently using the fuzzy match (which
            # risks clicking the wrong element), we surface the full
            # accessible name so the agent can retry with an exact selector.
            if count == 0 and exact and name is not None:
                fuzzy_locator = page.get_by_role(role, name=search_name, exact=False)  # type: ignore[arg-type]
                fuzzy_count = await fuzzy_locator.count()
                if fuzzy_count > 0:
                    # Collect accessible names of the fuzzy matches for the
                    # error message so the agent knows what to use instead.
                    suggestions: list[str] = []
                    for i in range(min(fuzzy_count, 5)):
                        try:
                            # Use JavaScript to compute the accessible name the same
                            # way Playwright does (follows ARIA spec)
                            aria_name = await fuzzy_locator.nth(i).evaluate(
                                """(el) => {
                                    // Normalize whitespace to match how Playwright processes names
                                    const normalize = (text) => text.replace(/\\s+/g, ' ').trim();

                                    // Try aria-label first
                                    const label = el.getAttribute('aria-label');
                                    if (label) return normalize(label);

                                    // Try aria-labelledby - use textContent to match ARIA spec
                                    // (Playwright includes hidden text per spec)
                                    const labelledby = el.getAttribute('aria-labelledby');
                                    if (labelledby) {
                                        const ids = labelledby.split(/\\s+/);
                                        const texts = ids.map(id => {
                                            const ref = document.getElementById(id);
                                            return ref ? normalize(ref.textContent) : '';
                                        }).filter(t => t);
                                        if (texts.length > 0) return texts.join(' ');
                                    }

                                    // Fallback to visible text
                                    return normalize(el.innerText || el.textContent || '');
                                }"""
                            )
                            if aria_name:
                                suggestions.append(f"{role}:{aria_name.strip()}")
                        except PlaywrightError:
                            pass

                    # Sort suggestions to prioritize prefix matches with the original search
                    # E.g., if searching "Delete Breathe Right...", rank "Delete ..." higher than "Add to cart, ..."
                    if suggestions and name:
                        # Extract first word from original search (e.g., "Delete", "Add", etc.)
                        original_prefix = name.split()[0] if name.split() else ""

                        def suggestion_priority(s: str) -> tuple[int, int]:
                            # Remove "role:" prefix to get just the name
                            suggestion_name = s.split(":", 1)[1] if ":" in s else s
                            suggestion_prefix = suggestion_name.split()[0] if suggestion_name.split() else ""

                            # Priority 0: exact prefix match (e.g., both start with "Delete")
                            # Priority 1: original is substring of suggestion (partial match)
                            # Priority 2: no prefix match
                            if suggestion_prefix.lower() == original_prefix.lower():
                                priority = 0
                            elif original_prefix.lower() in suggestion_name.lower():
                                priority = 1
                            else:
                                priority = 2

                            # Secondary sort: prefer shorter names (more specific)
                            length = len(suggestion_name)

                            return (priority, length)

                        suggestions.sort(key=suggestion_priority)

                    hint = (
                        f"No exact match for '{clean_target}'. "
                        f"Similar element(s) found — try: "
                        + ", ".join(f"'{s}'" for s in suggestions)
                        if suggestions
                        else f"No exact match for '{clean_target}', "
                        f"but {fuzzy_count} similar element(s) exist. "
                        f"Use view_page() to find the correct name."
                    )
                    raise BrowserToolError(hint, tool=tool_name)
        except PlaywrightError as exc:
            logger.debug("role:name lookup failed for %s: %s", clean_target, exc)
        else:
            selector_label = f"role={role}[name={name}]" if name else f"role={role}"
            if count > 0:
                # Explicit index: button:Add to Cart[1]
                if index is not None:
                    if index >= count:
                        msg = f"Index [{index}] out of range for '{role}:{name}' ({count} matches)."
                        raise BrowserToolError(msg, tool=tool_name)
                    return _LocatorResolution(
                        locator=role_locator.nth(index),
                        strategy="role_name",
                        query=clean_target,
                        match_count=count,
                        resolved_selector=f"{selector_label}[{index}]",
                    )

                # Single match — return directly
                if count == 1:
                    return _LocatorResolution(
                        locator=role_locator.first,
                        strategy="role_name",
                        query=clean_target,
                        match_count=1,
                        resolved_selector=selector_label,
                    )

                # Multiple matches — try viewport filtering
                if require_single_match:
                    viewport_locator, visible_count = await _filter_to_viewport(
                        role_locator, count, page,
                    )
                    if viewport_locator is not None:
                        return _LocatorResolution(
                            locator=viewport_locator,
                            strategy="role_name",
                            query=clean_target,
                            match_count=1,
                            resolved_selector=selector_label,
                        )
                    hint = f"'{role}:{name}[0]'" if name else f"'{role}:[0]'"
                    msg = (
                        f"'{clean_target}' matched {count} elements "
                        f"({visible_count} visible in viewport). "
                        f"Use view_page(scope=\"...\") to narrow, or add an "
                        f"index like {hint}."
                    )
                    raise BrowserToolError(msg, tool=tool_name)

                # require_single_match=False — return all
                return _LocatorResolution(
                    locator=role_locator,
                    strategy="role_name",
                    query=clean_target,
                    match_count=count,
                    resolved_selector=selector_label,
                )

    # 1) Selector handle (CSS selector or Playwright selector engine string).
    # Try this first since generated selectors from query tools are typically
    # CSS selectors (#id, [attr], tag >> nth=N) or Playwright text= selectors.
    # Attempting text match first would waste a round-trip and risk false-
    # positive matches (e.g., page text literally containing "#email").
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

    # 2) Exact visible text — fallback when the input isn't a valid selector
    # (e.g., user-typed plain text like "Sign in").
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
