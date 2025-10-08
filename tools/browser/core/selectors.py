"""Selector generation utilities for browser tools.

This module centralizes logic for constructing unique Playwright selectors for
DOM elements. Callers create a :class:`SelectorRegistry` for the current page
and request selectors through :func:`build_unique_selector`. The registry
tracks already issued selectors and ensures each returned selector is unique,
preferring inexpensive attribute-based strategies before falling back to more
expensive DOM walks.
"""

from __future__ import annotations
# ruff: noqa: I001  # Import sorting intentionally customized; project permits ignoring I001

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from playwright.async_api import ElementHandle
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
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
    needs_verification: bool = False
    notes: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class SelectorResult:
    """Selected unique selector along with metadata."""

    selector: str
    strategy: SelectorStrategy
    verified_unique: bool
    collision_count: int
    fallbacks_tried: tuple[SelectorStrategy, ...]


class SelectorRegistry:
    """Stateful selector registry that guarantees uniqueness for a page."""

    def __init__(self, page: Page) -> None:
        """Initialize the registry for ``page``."""
        self._page = page
        self._seen: dict[str, int] = {}

    def reset(self) -> None:
        """Reset internal tracking of issued selectors."""
        self._seen.clear()

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

            if candidate.needs_verification:
                is_unique = await _verify_selector_unique(self._page, candidate.selector)
                if not is_unique:
                    collisions += 1
                    logger.debug(
                        "Selector %s (%s) failed uniqueness verification",
                        candidate.selector,
                        candidate.strategy,
                    )
                    continue
                verified_unique = True
            else:
                verified_unique = False

            existing = self._seen.get(candidate.selector)
            if existing is None:
                self._seen[candidate.selector] = 1
                return SelectorResult(
                    selector=candidate.selector,
                    strategy=candidate.strategy,
                    verified_unique=verified_unique,
                    collision_count=collisions,
                    fallbacks_tried=tuple(attempts),
                )

            collisions += 1
            self._seen[candidate.selector] = existing + 1
            logger.debug(
                "Selector %s already issued %s time(s); collision recorded",
                candidate.selector,
                existing,
            )

        if not path_candidate:
            raise RuntimeError("Unable to generate fallback selector without DOM path")

        base_usage = self._seen.get(path_candidate.selector, 1)
        fallback_selector = await _augment_with_nth(
            path_candidate.selector,
            max(base_usage - 1, 0),
        )
        attempts.append(SelectorStrategy.FALLBACK)
        self._seen[fallback_selector] = 1
        return SelectorResult(
            selector=fallback_selector,
            strategy=SelectorStrategy.FALLBACK,
            verified_unique=False,
            collision_count=collisions,
            fallbacks_tried=tuple(attempts),
        )


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


async def _candidate_from_id(element: ElementHandle) -> SelectorCandidate | None:
    """Return selector candidate based on element ``id``."""
    try:
        value = await element.get_attribute("id")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read id attribute: %s", exc)
        return None
    if not value:
        return None
    selector = f"#{value}"
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.ID,
        cost=10,
        needs_verification=False,
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
                needs_verification=False,
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
        needs_verification=True,
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
    if "'" in aria_label:
        return None
    try:
        role = await element.get_attribute("role")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Failed to read role attribute: %s", exc)
        role = None

    selector = f"[role='{role}'][aria-label='{aria_label}']" if role else f"[aria-label='{aria_label}']"

    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.ARIA_ROLE_LABEL,
        cost=40,
        needs_verification=True,
        notes={"attribute": "aria-label", "role": role},
    )


def _candidate_from_text_exact(text: str) -> SelectorCandidate | None:
    """Return text selector candidate when ``text`` is short enough."""
    if not text or len(text) > MAX_TEXT_SELECTOR_LEN:
        return None
    escaped = text.replace('"', '\\"')
    selector = f'text="{escaped}"'
    return SelectorCandidate(
        selector=selector,
        strategy=SelectorStrategy.TEXT_EXACT,
        cost=50,
        needs_verification=True,
        notes={"text": text},
    )


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
        "  let parentSelector = parent.tagName.toLowerCase();"
        "  if (parent.id) {"
        "    parentSelector = '#' + parent.id;"
        "  } else if (parent.getAttribute('data-testid')) {"
        "    parentSelector = `[data-testid='${parent.getAttribute('data-testid')}']`;"
        "  }"
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
        needs_verification=True,
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
        "        segments.unshift('#' + current.id);"
        "        break;"
        "      }"
        "      let nth = 1;"
        "      let sibling = current;"
        "      while ((sibling = sibling.previousElementSibling)) {"
        "        if (sibling.nodeName === current.nodeName) {"
        "          nth++;"
        "        }"
        "      }"
        "      if (nth > 1) {"
        "        segment += ':nth-of-type(' + nth + ')';"
        "      }"
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
        needs_verification=False,
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
