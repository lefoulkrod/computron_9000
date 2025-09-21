"""Shared page snapshot models and extraction utilities.

This module centralizes logic for building a lightweight snapshot of a
Playwright ``Page`` after navigation or other interactions. It is intended
for internal consumption by browser tools that need to return a structured
summary of the current page state.

Design goals:
    * Small JSON-serializable models (Pydantic BaseModel)
    * Robust against intermittent Playwright extraction errors
    * Conservative field sizes (title/snippet/link text truncation)

Public export surface intentionally minimal; tools should import the models
and call ``_build_page_snapshot`` (prefixed underscore marks it internal) to
produce a ``PageSnapshot`` instance.
"""

from __future__ import annotations

import logging

from playwright.async_api import (
    ElementHandle,
    Page,
    Response,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Link(BaseModel):
    """Link info extracted from an anchor element.

    Attributes:
        text: Visible link text (trimmed to <=80 chars).
        href: Href attribute of the anchor.
        selector: CSS selector path to the anchor element.
    """

    text: str = Field(..., max_length=80)
    href: str
    selector: str = ""


class Form(BaseModel):
    """Form summary.

    Attributes:
        selector: Concise selector (action, id, or nth-of-type fallback).
        inputs: Collected names of form fields (excluding hidden/buttons).
    """

    selector: str
    inputs: list[str]


class PageSnapshot(BaseModel):
    """Structured snapshot of a web page."""

    title: str
    url: str
    snippet: str = Field(..., max_length=500)
    links: list[Link]
    forms: list[Form]
    status_code: int | None = None


async def _element_css_selector(element: ElementHandle) -> str:
    """Return a best-effort CSS selector path for an element.

    Uses an in-page evaluation of a small JS helper adapted from the provided
    ``cssPath`` snippet. Falls back to an empty string if evaluation fails.

    Args:
        element: Playwright ``ElementHandle`` to derive a selector for.

    Returns:
        A CSS selector string (e.g. ``"html > body > div:nth-of-type(2) > a"``) or
        an empty string on failure.
    """
    # Updated cssPath implementation prioritizing id, then unique class among siblings,
    # then building a path that leverages class names (joined) with an nth-of-type fallback.
    # Intentionally contains no test affordances or instrumentation.
    script = (
        "(el) => {"
        "function cssPath(el) {"
        "  if (!(el instanceof Element)) return '';"
        "  if (el.id) return '#' + el.id;"  # Fast path for id
        "  if (el.classList && el.classList.length > 0) {"
        "    const className = [...el.classList][0];"
        "    const siblings = el.parentNode ? el.parentNode.querySelectorAll('.' + className) : [];"
        "    if (siblings.length === 1) { return '.' + className; }"
        "  }"
        "  const path = [];"
        "  while (el && el.nodeType === Node.ELEMENT_NODE) {"
        "    let selector = el.nodeName.toLowerCase();"
        "    if (el.id) {"
        "      selector = '#' + el.id;"
        "      path.unshift(selector);"
        "      break;"
        "    } else if (el.classList && el.classList.length > 0) {"
        "      selector += '.' + [...el.classList].join('.');"
        "    } else {"
        "      let sib = el, nth = 1;"
        "      while ((sib = sib.previousElementSibling)) {"
        "        if (sib.nodeName.toLowerCase() === el.nodeName.toLowerCase()) nth++;"
        "      }"
        "      if (nth > 1) selector += ':nth-of-type(' + nth + ')';"
        "    }"
        "    path.unshift(selector);"
        "    el = el.parentNode;"
        "  }"
        "  return path.join(' > ');"
        "}"
        "try { return cssPath(el) || ''; } catch (e) { return ''; }"
        "}"
    )
    try:
        selector: str = await element.evaluate(script)
    except (PlaywrightError, AttributeError) as exc:  # pragma: no cover - defensive
        logger.debug("Failed to compute element CSS selector: %s", exc)
        return ""
    else:
        return selector


async def _extract_links(page: Page, limit: int = 20) -> list[Link]:
    """Extract up to ``limit`` anchor elements with text and href.

    Args:
        page: Playwright Page-like object.
        limit: Maximum number of links to include.

    Returns:
        List of ``Link`` objects.
    """
    links: list[Link] = []
    try:
        anchors = await page.query_selector_all("a")
    except PlaywrightError:  # pragma: no cover - defensive
        anchors = None

    if not anchors:
        return links

    for a in anchors[:limit]:
        try:
            text_val = await a.inner_text()
            href_val = await a.get_attribute("href")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Skipping anchor due to error: %s", exc)
            continue
        text = (text_val or "").strip()
        href = href_val or ""
        if text and href:
            try:
                selector = await _element_css_selector(a)
            except PlaywrightError:  # pragma: no cover - defensive
                selector = ""
            links.append(Link(text=text[:80], href=href, selector=selector))
    return links


async def _extract_forms(page: Page) -> list[Form]:
    """Extract a minimal description of forms on the page."""
    forms: list[Form] = []
    try:
        form_elements = await page.query_selector_all("form")
    except PlaywrightError:  # pragma: no cover - defensive
        form_elements = None

    if not form_elements:
        return forms

    for idx, form_el in enumerate(form_elements, start=1):
        try:
            action = await form_el.get_attribute("action")
            form_id = await form_el.get_attribute("id")
        except PlaywrightError:  # pragma: no cover - defensive
            action = None
            form_id = None

        if action:
            selector = f"form[action='{action}']"
        elif form_id:
            selector = f"form#{form_id}"
        else:
            selector = f"form:nth-of-type({idx})"

        inputs: list[str] = []
        try:
            fields = await form_el.query_selector_all("input, textarea, select")
            for field in fields:
                try:
                    tag = await field.evaluate("(el) => el.tagName.toLowerCase()")
                    if tag == "input":
                        input_type = await field.get_attribute("type")
                        if (input_type or "").lower() in {
                            "hidden",
                            "submit",
                            "button",
                            "image",
                            "reset",
                            "file",
                        }:
                            continue
                    name_attr = await field.get_attribute("name")
                    if name_attr:
                        inputs.append(name_attr)
                except PlaywrightError:  # pragma: no cover - defensive
                    continue
        except PlaywrightError:  # pragma: no cover - defensive
            inputs = []

        forms.append(Form(selector=selector, inputs=inputs))
    return forms


async def _build_page_snapshot(page: Page, response: Response | None) -> PageSnapshot:
    """Internal helper to construct a ``PageSnapshot`` from a page & response.

    Args:
        page: A Playwright Page instance after navigation/interactions.
        response: The primary navigation response (may be ``None``).

    Returns:
        ``PageSnapshot`` instance populated with extracted metadata.
    """
    try:
        title: str = await page.title()
    except PlaywrightError:  # pragma: no cover - defensive
        title = ""

    if response is not None:
        final_url = response.url
        status_code = response.status
    else:
        final_url = page.url
        status_code = None

    try:
        body_text: str = await page.inner_text("body")
    except PlaywrightError:  # pragma: no cover - defensive
        body_text = ""
    snippet = (body_text or "").strip()[:500]

    links = await _extract_links(page)
    forms = await _extract_forms(page)

    return PageSnapshot(
        title=title,
        url=final_url,
        snippet=snippet,
        links=links,
        forms=forms,
        status_code=status_code,
    )


__all__ = ["Form", "Link", "PageSnapshot", "_build_page_snapshot"]
