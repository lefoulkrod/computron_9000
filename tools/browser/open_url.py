"""Simple browser tool: open a URL and return title, url, snippet, links, forms, status.

This tool uses the shared persistent Playwright browser context from
``tools.browser.core``. It opens a new page, navigates to the URL, and extracts:

- title: page title
- url: the final URL after any redirects
- snippet: first 500 characters of the page's visible body text
- links: up to 20 anchor elements with non-empty text and href (text trimmed to 80 chars)
- forms: simple summary of forms on the page (CSS selector + input names)
- status_code: HTTP status of the navigation, if available

Returns Pydantic models for safe, JSON-serializable results.
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

from tools.browser.core import get_browser
from tools.browser.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


class OpenUrlLink(BaseModel):
    """Link info extracted from an anchor element.

    Attributes:
        text: The visible text of the link (trimmed to at most 80 characters).
        href: The href attribute value of the anchor.
    """

    text: str = Field(..., max_length=80)
    href: str


class OpenUrlResult(BaseModel):
    """Result of opening a URL in a headless browser.

    Attributes:
        title: The page title as reported by the browser.
        url: The final URL after any redirects.
        snippet: First 500 characters of the page's visible body text.
        links: Up to 20 links found on the page.
        forms: Forms found on the page (best-effort summary).
        status_code: HTTP status code of the main navigation if available.
    """

    title: str
    url: str
    snippet: str = Field(..., max_length=500)
    links: list[OpenUrlLink]
    forms: list[OpenUrlForm]
    status_code: int | None = None


class OpenUrlForm(BaseModel):
    """Form info extracted from a form element.

    Attributes:
        selector: A concise CSS selector for the form (prefers action, then id, then nth-of-type).
        inputs: List of input field names (input/textarea/select) excluding buttons and hidden.
    """

    selector: str
    inputs: list[str]


async def open_url(url: str) -> OpenUrlResult:
    """Open a URL in the shared browser and return a compact summary.

    Args:
        url: The URL to open (http/https).

    Returns:
        OpenUrlResult: Pydantic model with title, url, snippet, links, forms, status_code.

    Raises:
    BrowserToolError: If navigation or extraction fails.
    """
    page: Any | None = None
    try:
        browser = await get_browser()
        page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded")

        title: str = await page.title()
        final_url: str = response.url if response is not None else page.url
        status_code: int | None = response.status if response is not None else None
        # crude visible text: grab body innerText, clip length
        body_text: str = await page.inner_text("body")
        snippet: str = (body_text or "").strip()[:500]

        anchors = await page.query_selector_all("a")
        links: list[OpenUrlLink] = []
        for a in anchors[:20]:
            try:
                text_val = await a.inner_text()
                href_val = await a.get_attribute("href")
            except PlaywrightError as exc:  # pragma: no cover - defensive for odd elements
                logger.warning("Skipping anchor due to extraction error: %s", exc)
                continue
            text = (text_val or "").strip()
            href = href_val or ""
            if text and href:
                # Pydantic enforces max length; we also pre-trim
                links.append(OpenUrlLink(text=text[:80], href=href))

        # Extract basic form info: selector + input names
        forms: list[OpenUrlForm] = []
        try:
            form_elements = await page.query_selector_all("form")
            for idx, form in enumerate(form_elements, start=1):
                try:
                    action = await form.get_attribute("action")
                    form_id = await form.get_attribute("id")
                except PlaywrightError:
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
                    fields = await form.query_selector_all("input, textarea, select")
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
                        except PlaywrightError:
                            continue
                except PlaywrightError:
                    inputs = []

                forms.append(OpenUrlForm(selector=selector, inputs=inputs))
        except PlaywrightError:
            forms = []

        return OpenUrlResult(
            title=title,
            url=final_url,
            snippet=snippet,
            links=links,
            forms=forms,
            status_code=status_code,
        )

    except Exception as exc:  # gather any failure into unified error for upstream simplicity
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc
