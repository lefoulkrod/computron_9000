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

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Link(BaseModel):
    """Link info extracted from an anchor element.

    Attributes:
        text: Visible link text (trimmed to <=80 chars).
        href: Href attribute of the anchor.
    """

    text: str = Field(..., max_length=80)
    href: str


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
            links.append(Link(text=text[:80], href=href))
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
