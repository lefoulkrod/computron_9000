"""Internal DOM utility helpers for snapshot extraction.

These helpers are intentionally small and internal (underscore-prefixed) to avoid
expanding the public surface area of browser tools. They centralize common
Playwright property/attribute fallback logic so behavior stays consistent across
control types.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast, runtime_checkable

from playwright.async_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

__all__ = ["_DOMBoolHandle", "_element_bool_state"]


@runtime_checkable
class _DOMBoolHandle(Protocol):
    """Protocol representing the subset of methods used for boolean state extraction.

    Both real Playwright ``ElementHandle`` objects and test fakes can satisfy this
    by implementing ``evaluate`` (async) and/or ``get_attribute`` (async). Each
    method returns awaitables. We keep return types as ``Any`` because Playwright
    evaluation is dynamically typed.
    """

    async def evaluate(self, script: str) -> Any:  # pragma: no cover - structural
        ...

    async def get_attribute(self, name: str) -> Any:  # pragma: no cover - structural
        ...


async def _element_bool_state(
    handle: _DOMBoolHandle | object,
    *,
    prop_script: str,
    attr: str,
    default: bool = False,
    context: str | None = None,
) -> bool:
    """Return a boolean DOM state with property preference and attribute fallback.

    Args:
        handle: Playwright element/option handle (or test fake providing evaluate/get_attribute).
        prop_script: JavaScript arrow function body string (e.g. ``"el => el.checked === true"``)
            that should return a boolean when evaluated.
        attr: Attribute name used as a fallback (presence => True) if property evaluation fails.
        default: Value to return if both property evaluation and attribute read fail.
        context: Optional short context label (e.g. "checkbox", "radio", "select_option") used
            in debug logging when falling back to default.

    Returns:
        Boolean state derived from property, attribute, or the provided default.
    """
    # Attempt property evaluation first
    evaluate_fn = getattr(handle, "evaluate", None)
    if callable(evaluate_fn):  # runtime path with Playwright / enriched test double
        try:
            result = await cast(Any, evaluate_fn)(prop_script)
            if isinstance(result, bool):  # accept only explicit boolean
                return result
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Property evaluate failed (%s attr=%s): %s", context or "state", attr, exc)
    else:
        logger.debug(
            "Handle has no evaluate method for property check (%s attr=%s); attempting attribute fallback",
            context or "state",
            attr,
        )

    # Attribute fallback
    get_attr_fn = getattr(handle, "get_attribute", None)
    if callable(get_attr_fn):
        try:
            present = await cast(Any, get_attr_fn)(attr)
            return present is not None
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug(
                "Attribute read failed (%s attr=%s), returning default=%s: %s",
                context or "state",
                attr,
                default,
                exc,
            )
            return default
    # Final default path
    logger.debug(
        "No attribute reader available (%s attr=%s), returning default=%s",
        context or "state",
        attr,
        default,
    )
    return default
