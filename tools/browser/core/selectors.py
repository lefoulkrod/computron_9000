"""Selector generation utilities for browser tools.

This module centralizes logic for constructing unique Playwright selectors for
DOM elements. Callers create a :class:`SelectorRegistry` for the current page
and request selectors through :func:`build_unique_selector`. The registry
tracks already issued selectors and ensures each returned selector is unique,
preferring inexpensive attribute-based strategies before falling back to more
expensive DOM walks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from playwright.async_api import ElementHandle, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

MAX_TEXT_SELECTOR_LEN = 200


class SelectorStrategy(Enum):
    """Enumeration of selector strategies ordered roughly by preference."""

    ID = auto()
    DATA_ATTRIBUTE = auto()
    NAME_ATTRIBUTE = auto()
    ARIA_ROLE_LABEL = auto()
    TEXT_EXACT = auto()
    TEXT_SUBSTRING = auto()
    DOM_POSITION = auto()
    DOM_PATH = auto()
    FALLBACK = auto()


@dataclass(slots=True, frozen=True)
class SelectorCandidate:
    """Potential selector string returned by heuristic helpers."""

    selector: str
    strategy: SelectorStrategy
    cost: int
    notes: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class SelectorResult:
    """Selected unique selector along with metadata."""

    selector: str
    strategy: SelectorStrategy
    collision_count: int
    fallbacks_tried: tuple[SelectorStrategy, ...]


class SelectorRegistry:
    """Stateful selector registry that guarantees uniqueness for a page."""

    def __init__(self, page: Page) -> None:
        """Initialize the registry for ``page``."""
        self._page = page
        self._seen: dict[str, int] = {}
        self._fallback_counts: dict[str, int] = {}

    def reset(self) -> None:
        """Reset internal tracking of issued selectors."""
        self._seen.clear()
        self._fallback_counts.clear()

    def seen(self) -> frozenset[str]:
        """Return a frozen set of selectors issued so far."""
        return frozenset(self._seen.keys())

    async def register(
        self,
        element: ElementHandle,
        *,
        tag: str | None = None,
        text: str | None = None,
    ) -> SelectorResult:
        """Return a unique selector for ``element`` using ordered strategies.

        Args:
            element: Playwright element handle.
            tag: Optional known tag name to avoid redundant round-trips.
            text: Visible text associated with the element.

        Returns:
            SelectorResult with strategy and collision metadata.
        """
        normalized_text = _normalize_text_for_selector(text)
        candidates: list[SelectorCandidate] = []

        candidate = await _candidate_from_id(element)
        if candidate:
            candidates.append(candidate)

        data_candidate = await _candidate_from_data_attribute(element)
        if data_candidate:
            candidates.append(data_candidate)

        name_candidate = await _candidate_from_name(element, tag=tag)
        if name_candidate:
            candidates.append(name_candidate)

        aria_candidate = await _candidate_from_role_label(element)
        if aria_candidate:
            candidates.append(aria_candidate)

        if normalized_text:
            text_candidate = _candidate_from_text_exact(normalized_text)
            if text_candidate:
                candidates.append(text_candidate)

            # Try substring selector for longer text
            substring_candidate = _candidate_from_text_substring(normalized_text)
            if substring_candidate:
                candidates.append(substring_candidate)

        position_candidate = await _candidate_from_dom_position(element, tag=tag)
        if position_candidate:
            candidates.append(position_candidate)

        path_candidate = await _candidate_from_dom_path(element)
        if path_candidate:
            candidates.append(path_candidate)

        collisions = 0
        attempts: list[SelectorStrategy] = []
        for candidate in sorted(candidates, key=lambda item: item.cost):
            if not candidate.selector:
                continue

            attempts.append(candidate.strategy)

            # Check if selector already used in this session
            if candidate.selector in self._seen:
                collisions += 1
                logger.debug(
                    "Selector %s already issued; collision recorded",
                    candidate.selector,
                )
                continue

            # Verify uniqueness on page
            is_unique = await _verify_selector_unique(self._page, candidate.selector)
            if is_unique:
                self._seen[candidate.selector] = 1
                return SelectorResult(
                    selector=candidate.selector,
                    strategy=candidate.strategy,
                    collision_count=collisions,
                    fallbacks_tried=tuple(attempts),
                )

            # Not unique - for text selectors, try adding >> nth=0
            if candidate.strategy in (SelectorStrategy.TEXT_EXACT, SelectorStrategy.TEXT_SUBSTRING):
                nth_selector = f"{candidate.selector} >> nth=0"
                is_nth_unique = await _verify_selector_unique(self._page, nth_selector)
                if is_nth_unique and nth_selector not in self._seen:
                    self._seen[nth_selector] = 1
                    logger.debug(
                        "Text selector %s augmented with nth=0 for uniqueness",
                        candidate.selector,
                    )
                    return SelectorResult(
                        selector=nth_selector,
                        strategy=candidate.strategy,
                        collision_count=collisions,
                        fallbacks_tried=tuple(attempts),
                    )

            collisions += 1
            logger.debug(
                "Selector %s (%s) failed uniqueness verification",
                candidate.selector,
                candidate.strategy,
            )

        if not path_candidate:
            raise RuntimeError("Unable to generate fallback selector without DOM path")

        attempts.append(SelectorStrategy.FALLBACK)
        base_selector = path_candidate.selector
        suffix = self._fallback_counts.get(base_selector, 0)
        max_attempts = 50
        while max_attempts > 0:
            fallback_selector = await _augment_with_nth(base_selector, suffix)
            is_unique = await _verify_selector_unique(self._page, fallback_selector)
            if is_unique and fallback_selector not in self._seen:
                self._seen[fallback_selector] = 1
                self._fallback_counts[base_selector] = suffix + 1
                return SelectorResult(
                    selector=fallback_selector,
                    strategy=SelectorStrategy.FALLBACK,
                    collision_count=collisions,
                    fallbacks_tried=tuple(attempts),
                )

            collisions += 1
            suffix += 1
            max_attempts -= 1
            logger.debug(
                "Fallback selector %s failed uniqueness; retrying with suffix %s",
                fallback_selector,
                suffix,
            )

        raise RuntimeError("Unable to generate unique fallback selector after multiple attempts")


async def build_unique_selector(
    element: ElementHandle,
    *,
    tag: str | None = None,
    text: str | None = None,
    registry: SelectorRegistry,
) -> SelectorResult:
    """Build a unique selector for ``element`` using ``context`` registry."""
    return await registry.register(
        element,
        tag=tag,
        text=text,
    )


# Characters in element IDs that break CSS "#id" selector syntax.
# Using [id='...'] attribute selector avoids escaping issues entirely.
_CSS_SPECIAL_CHARS = frozenset(":.[]()+~>*^$|/\\")


async def _candidate_from_id(element: ElementHandle) -> SelectorCandidate | None:
    """Return selector candidate based on element ``id``."""
    try:
        value = await element.get_attribute("id")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read id attribute: %s", exc)
        return None
    if not value:
        return None
    # Use attribute selector form when the ID contains characters that would
    # be invalid or ambiguous in CSS "#id" syntax (e.g., :r1:, foo.bar, a[0]),
    # or when the ID starts with a digit (which is invalid in CSS).
    if any(ch in value for ch in _CSS_SPECIAL_CHARS) or value[0].isdigit():
        # Escape single quotes inside the value for the attribute selector
        escaped = value.replace("'", "\\'")
        selector = f"[id='{escaped}']"
    else:
        selector = f"#{value}"
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.ID,
        cost=10,
        notes={"attribute": "id"},
    )


async def _candidate_from_data_attribute(element: ElementHandle) -> SelectorCandidate | None:
    """Return candidate from common ``data-test`` style attributes."""
    attributes = ("data-testid", "data-test", "data-qa", "data-cy")
    for attr in attributes:
        try:
            value = await element.get_attribute(attr)
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to read %s attribute: %s", attr, exc)
            continue
        if value:
            selector = f"[{attr}='{value}']"
            return SelectorCandidate(
                selector=selector,
                strategy=SelectorStrategy.DATA_ATTRIBUTE,
                cost=20,
                notes={"attribute": attr},
            )
    return None


async def _candidate_from_name(
    element: ElementHandle,
    *,
    tag: str | None,
) -> SelectorCandidate | None:
    """Return selector candidate based on ``name`` attribute for form fields."""
    try:
        value = await element.get_attribute("name")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read name attribute: %s", exc)
        return None

    if not value:
        return None

    if tag is None:
        try:
            tag = await element.evaluate("(node) => node.tagName.toLowerCase()")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to evaluate tag for name attribute: %s", exc)
            return None

    selector_prefix = tag or ""
    if tag == "input":
        try:
            input_type = await element.get_attribute("type")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to read type attribute for input: %s", exc)
            input_type = None
        if input_type:
            selector_prefix = f"input[type='{input_type}']"
    selector = f"{selector_prefix}[name='{value}']" if selector_prefix else f"[name='{value}']"
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.NAME_ATTRIBUTE,
        cost=30,
        notes={"attribute": "name"},
    )


async def _candidate_from_role_label(element: ElementHandle) -> SelectorCandidate | None:
    """Return selector candidate combining role and aria-label."""
    try:
        aria_label = await element.get_attribute("aria-label")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read aria-label attribute: %s", exc)
        return None
    if not aria_label:
        return None
    # Reject values containing characters that break CSS attribute selectors
    _unsafe_for_css_attr = frozenset("'\"]\\")
    if any(ch in aria_label for ch in _unsafe_for_css_attr):
        return None
    try:
        role = await element.get_attribute("role")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read role attribute: %s", exc)
        role = None
    # Also reject role values with unsafe characters
    if role and any(ch in role for ch in _unsafe_for_css_attr):
        role = None

    selector = f"[role='{role}'][aria-label='{aria_label}']" if role else f"[aria-label='{aria_label}']"

    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.ARIA_ROLE_LABEL,
        cost=40,
        notes={"attribute": "aria-label", "role": role},
    )


def _escape_text_for_selector(text: str) -> str:
    """Escape text for use in Playwright text="..." selectors."""
    # Backslash must be escaped first to avoid double-escaping
    result = text.replace("\\", "\\\\")
    result = result.replace('"', '\\"')
    # Collapse whitespace (newlines, tabs, etc.) to single spaces
    result = " ".join(result.split())
    return result


def _candidate_from_text_exact(text: str) -> SelectorCandidate | None:
    """Return text selector candidate when ``text`` is short enough."""
    if not text or len(text) > MAX_TEXT_SELECTOR_LEN:
        return None
    escaped = _escape_text_for_selector(text)
    selector = f'text="{escaped}"'
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.TEXT_EXACT,
        cost=50,
        notes={"text": text},
    )


def _candidate_from_text_substring(text: str) -> SelectorCandidate | None:
    """Return text substring selector using first line or up to 60 chars.

    For long text, extract a unique identifier (first line or first ~60 chars)
    and create a substring selector. This is useful for elements with lots of
    metadata where only the first part is distinctive.
    """
    if not text:
        return None

    # Try first line (up to first newline)
    first_line = text.split("\n")[0].strip()
    if first_line and 10 <= len(first_line) <= MAX_TEXT_SELECTOR_LEN:
        escaped = _escape_text_for_selector(first_line)
        selector = f'text="{escaped}"'
        return SelectorCandidate(
            selector=selector,
            strategy=SelectorStrategy.TEXT_SUBSTRING,
            cost=55,
            notes={"text": first_line, "original_length": len(text)},
        )

    # If first line too short/long, try first ~60 chars
    if len(text) > MAX_TEXT_SELECTOR_LEN:
        substring = text[:60].strip()
        if len(substring) >= 10:
            escaped = _escape_text_for_selector(substring)
            selector = f'text="{escaped}"'
            return SelectorCandidate(
                selector=selector,
                strategy=SelectorStrategy.TEXT_SUBSTRING,
                cost=55,
                notes={"text": substring, "original_length": len(text)},
            )

    return None


async def _candidate_from_dom_position(
    element: ElementHandle,
    *,
    tag: str | None,
) -> SelectorCandidate | None:
    """Return a positional selector scoped to the parent element."""
    script = (
        "(node) => {"
        "  if (!node || !node.parentElement) { return null; }"
        "  const tagName = node.tagName.toLowerCase();"
        "  const parent = node.parentElement;"
        "  const siblings = Array.from(parent.children).filter("
        "    (child) => child.tagName.toLowerCase() === tagName"
        "  );"
        "  const index = siblings.indexOf(node);"
        "  if (index < 0) { return null; }"
        "  const nth = index + 1;"
        "  function escapeToken(token) {"
        "    return token.replace(/([\\\\.:#\\[\\],>+~ *'$\"])/g, (m) => `\\\\${m}`);"
        "  }"
        "  const segments = [];"
        "  let current = parent;"
        "  const MAX_DEPTH = 6;"
        "  let depth = 0;"
        "  while (current && depth < MAX_DEPTH) {"
        "    depth += 1;"
        "    if (current.id) {"
        "      segments.unshift('#' + escapeToken(current.id));"
        "      break;"
        "    }"
        "    const dataTest = current.getAttribute('data-testid');"
        "    if (dataTest) {"
        "      segments.unshift(`[data-testid='${escapeToken(dataTest)}']`);"
        "      break;"
        "    }"
        "    const classList = Array.from(current.classList).filter(Boolean);"
        "    if (classList.length > 0) {"
        "      segments.unshift('.' + escapeToken(classList[0]));"
        "      break;"
        "    }"
        "    const tag = current.tagName.toLowerCase();"
        "    let nthParent = 1;"
        "    let sib = current;"
        "    while ((sib = sib.previousElementSibling)) {"
        "      if (sib.tagName.toLowerCase() === tag) {"
        "        nthParent += 1;"
        "      }"
        "    }"
        "    segments.unshift(tag + `:nth-of-type(${nthParent})`);"
        "    current = current.parentElement;"
        "  }"
        "  if (segments.length === 0) {"
        "    const tag = parent.tagName.toLowerCase();"
        "    let nthParent = 1;"
        "    let sib = parent;"
        "    while ((sib = sib.previousElementSibling)) {"
        "      if (sib.tagName.toLowerCase() === tag) {"
        "        nthParent += 1;"
        "      }"
        "    }"
        "    segments.unshift(tag + `:nth-of-type(${nthParent})`);"
        "  }"
        "  const parentSelector = segments.join(' > ');"
        "  return {"
        "    tagName,"
        "    nth,"
        "    parentSelector,"
        "  };"
        "}"
    )

    try:
        data = await element.evaluate(script)
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to evaluate DOM position: %s", exc)
        return None

    if not data:
        return None

    tag_name = data.get("tagName")
    nth = data.get("nth")
    parent_selector = data.get("parentSelector")
    if not tag_name or not nth or not parent_selector:
        return None

    selector = f"{parent_selector} > {tag_name}:nth-of-type({nth})"
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.DOM_POSITION,
        cost=70,
        notes={"nth": nth, "parent": parent_selector},
    )


async def _candidate_from_dom_path(element: ElementHandle) -> SelectorCandidate | None:
    """Return a full DOM path selector for the element."""
    script = (
        "(node) => {"
        "  try {"
        "    if (!node || !(node instanceof Element)) {"
        "      return '';"
        "    }"
        "    const segments = [];"
        "    let current = node;"
        "    while (current && current.nodeType === Node.ELEMENT_NODE) {"
        "      let segment = current.nodeName.toLowerCase();"
        "      if (current.id) {"
        # Use attribute selector for IDs that start with digits or contain special chars
        "        const id = current.id;"
        "        const startsWithDigit = /^[0-9]/.test(id);"
        "        const hasSpecialChars = /[:.[\\]()+~>*^$|\\/\\\\]/.test(id);"
        "        if (startsWithDigit || hasSpecialChars) {"
        "          const escaped = id.replace(/'/g, \"\\\\'\");"
        '          segments.unshift("[id=\'" + escaped + "\']");'
        "        } else {"
        "          segments.unshift('#' + id);"
        "        }"
        "        break;"
        "      }"
        "      let nth = 1;"
        "      let sibling = current;"
        "      while ((sibling = sibling.previousElementSibling)) {"
        "        if (sibling.nodeName === current.nodeName) {"
        "          nth++;"
        "        }"
        "      }"
        "      segment += ':nth-of-type(' + nth + ')';"
        "      segments.unshift(segment);"
        "      current = current.parentElement;"
        "    }"
        "    return segments.join(' > ');"
        "  } catch (error) {"
        "    return '';"
        "  }"
        "}"
    )

    try:
        selector = await element.evaluate(script)
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to evaluate DOM path: %s", exc)
        return None

    if not selector:
        return None

    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.DOM_PATH,
        cost=80,
        notes={"source": "dom-path"},
    )


def _normalize_text_for_selector(text: str | None) -> str | None:
    """Normalize text for use in selectors."""
    if text is None:
        return None
    normalized = " ".join(text.split()).strip()
    return normalized or None


async def _verify_selector_unique(page: Page, selector: str) -> bool:
    """Return ``True`` when ``selector`` matches a single element on ``page``."""
    try:
        locator = page.locator(selector)
        count = await locator.count()
    except PlaywrightTimeoutError:
        logger.debug("Selector %s verification timed out", selector)
        return False
    except (PlaywrightError, AttributeError) as exc:
        logger.debug("Selector %s verification failed: %s", selector, exc)
        return False
    return count == 1


async def _augment_with_nth(selector: str, collision_index: int) -> str:
    """Return selector with a deterministic ``nth`` suffix."""
    suffix = collision_index
    if suffix < 0:
        suffix = 0
    return f"{selector} >> nth={suffix}"


__all__ = [
    "SelectorCandidate",
    "SelectorRegistry",
    "SelectorResult",
    "SelectorStrategy",
    "build_unique_selector",
]
