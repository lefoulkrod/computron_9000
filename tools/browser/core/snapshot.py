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

from playwright.async_api import ElementHandle, Page, Response
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_ELEMENT_TEXT_LEN = 120
MAX_ARIA_LABEL_LEN = 40


async def _fast_element_selector(el: ElementHandle, tag: str | None = None) -> str | None:
    """Return a quick, valid CSS selector using only cheap attribute reads.

    This helper prefers inexpensive attribute reads and returns a concise
    selector when possible. Callers should prefer using ``_best_selector``
    which orchestrates a fast-path attempt via this function and falls back
    to ``_element_css_selector`` when this returns ``None``.

    Heuristics (in priority order):
        1. id -> ``#id``
        2. data-testid/test/qa/cy -> ``[data-testid="val"]`` etc.
        3. form: id or action
        4. input/textarea/select: name (+ type for input)
        5. anchor: href (non-empty, not '#', not javascript:)
        6. button: id, name, or type=submit
        7. aria-label + role combination
    Falls back to ``None`` if no succinct selector available.
    Only produces pure CSS (no :has-text, no Playwright-specific selectors).
    """
    try:
        tag_name = tag or await el.evaluate("(n)=>n.tagName.toLowerCase()")
    except PlaywrightError:  # pragma: no cover - defensive
        return None

    # 1. id
    try:
        el_id = await el.get_attribute("id")
    except PlaywrightError:  # pragma: no cover - defensive
        el_id = None
    if el_id:
        return f"#{el_id}"

    # 2. data-* test hooks
    for attr in ("data-testid", "data-test", "data-qa", "data-cy"):
        try:
            val = await el.get_attribute(attr)
        except PlaywrightError:  # pragma: no cover - defensive
            val = None
        if val:
            return f"[{attr}='{val}']"

    # 3. form specifics
    if tag_name == "form":
        try:
            action = await el.get_attribute("action")
        except PlaywrightError:
            action = None
        if action:
            return f"form[action='{action}']"
        # (id already handled)

    # 4. inputs / fields
    if tag_name in {"input", "textarea", "select"}:
        try:
            name_attr = await el.get_attribute("name")
        except PlaywrightError:
            name_attr = None
        if name_attr:
            if tag_name == "input":
                try:
                    input_type = await el.get_attribute("type")
                except PlaywrightError:  # pragma: no cover - defensive
                    input_type = None
                if input_type:
                    return f"input[type='{input_type}'][name='{name_attr}']"
            return f"{tag_name}[name='{name_attr}']"

    # 5. anchors by href
    if tag_name == "a":
        try:
            href_val = await el.get_attribute("href")
        except PlaywrightError:  # pragma: no cover - defensive
            href_val = None
        if href_val and href_val not in {"#", "javascript:void(0)", "javascript:;"}:
            return f"a[href='{href_val}']"

    # 6. button semantics
    if tag_name == "button":
        try:
            name_attr = await el.get_attribute("name")
        except PlaywrightError:
            name_attr = None
        if name_attr:
            return f"button[name='{name_attr}']"
        try:
            type_attr = await el.get_attribute("type")
        except PlaywrightError:
            type_attr = None
        if type_attr == "submit":
            return "button[type='submit']"

    # 7. aria-label + role (Prefer label alone if short)
    try:
        aria_label = await el.get_attribute("aria-label")
    except PlaywrightError:
        aria_label = None
    if aria_label and 0 < len(aria_label) <= MAX_ARIA_LABEL_LEN and "'" not in aria_label:
        return f"[aria-label='{aria_label}']"

    # role only if combined? (skip to keep selector concise)
    return None


class Element(BaseModel):
    """Generic element returned in a page snapshot.

    Attributes:
        text: The inner visible text of the element. If truncated,
            the text ends with " (truncated)".
        role: Value of the ``role`` attribute if present.
        selector: A selector that can be used to interact with the element.
        tag: Lower-case tag name (e.g. ``a``, ``form``).
        href: Optional href for anchor-like elements.
        src: Optional source URL for elements that expose it (for example, ``iframe.src``).
        fields: For form elements, a list of collected form field metadata.
        action: For form elements, the form action attribute if any.
    """

    text: str = Field(..., max_length=140)
    role: str | None = None
    selector: str
    tag: str
    href: str | None = None
    # For form elements, collected fields with metadata (replaces legacy `inputs`)
    fields: list[FormField] | None = None
    action: str | None = None
    # Optional src attribute for elements like iframes
    src: str | None = None


class FormField(BaseModel):
    """Metadata for a single form control within a form element.

    Attributes:
        selector: A CSS selector that targets the field from the page root.
        name: The value of the ``name`` attribute when present.
        field_type: The control type (for inputs this is the ``type`` attr,
            otherwise the tag name such as ``textarea`` or ``select``).
        placeholder: The ``placeholder`` attribute value when present.
        required: Whether the control has the ``required`` attribute.
        options: For ``select`` elements, a list of option dicts with
            ``value`` and ``label`` keys representing option value and
            visible text respectively.
    """

    selector: str
    name: str | None = None
    field_type: str
    placeholder: str | None = None
    required: bool = False
    options: list[dict] | None = None


class PageSnapshot(BaseModel):
    """Structured snapshot of a web page.

    Attributes:
        title: Page ``<title>`` text (empty string on failure).
        url: Final URL (navigation response URL if available, else current ``page.url``).
        snippet: First 500 characters of visible ``<body>`` text (trimmed & truncated).
        elements: Interactive elements: up to 20 anchors plus all forms, plus
            buttons and iframes. Anchor or button ``text`` may end with
            " (truncated)" if clipped. Form entries use selector string as
            ``text``/``name``. Iframe entries include an optional ``src`` field.
        status_code: HTTP status code from the main navigation response or ``None`` if unavailable.
    """

    title: str
    url: str
    snippet: str = Field(..., max_length=500)
    elements: list[Element]
    status_code: int | None = None


async def _element_css_selector(element: ElementHandle) -> str:
    r"""Return a best-effort full CSS selector path for an element.

    Strategy (executed inside the page so it has direct DOM access):
    1. Walk ancestors up to but excluding the document root collecting a segment per node.
    2. For each node prefer:
       * ``#id`` when present (and stop - an id makes the remainder unique).
       * Otherwise the tag name plus a stable class token subset (first 2 class names) with
         Tailwind-style classes escaped (``:`` -> ``\\:``) to remain valid CSS.
       * When no classes, append an ``:nth-of-type(n)`` pseudo if there is more than one
         sibling of the same tag before it.
    3. Join segments with `` > ``. If generation fails return an empty string so callers
       can degrade gracefully.
    This produces selectors that are readable yet usually robust enough to re-select the
    element in subsequent interactions without being overly verbose (we stop early on id).
    """
    # Note: Prefer callers to use ``_best_selector`` which will attempt
    # the fast-path in ``_fast_element_selector`` before invoking this
    # more-expensive DOM-walking fallback.
    script = (
        "(el) => {"
        "  try {"
        "    if (!el || !(el instanceof Element)) return '';"
        "    const escapeClass = (cls) => cls.replace(/:/g, '\\:');"
        "    const segments = [];"
        "    let current = el;"
        "    while (current && current.nodeType === Node.ELEMENT_NODE) {"
        "      let seg = current.nodeName.toLowerCase();"
        "      if (current.id) {"
        "        seg = '#' + current.id;"
        "        segments.unshift(seg);"
        "        break;"
        "      } else {"
        "        if (current.classList && current.classList.length) {"
        "          const classes = [...current.classList].slice(0,2).map(escapeClass);"
        "          if (classes.length) { seg += '.' + classes.join('.'); }"
        "        }"
        "        let nth = 1; let sib = current;"
        "        while ((sib = sib.previousElementSibling)) {"
        "          if (sib.nodeName === current.nodeName) nth++;"
        "        }"
        "        if (nth > 1) { seg += ':nth-of-type(' + nth + ')'; }"
        "      }"
        "      segments.unshift(seg);"
        "      current = current.parentElement;"
        "    }"
        "    return segments.join(' > ');"
        "  } catch (e) { return ''; }"
        "}"
    )
    try:
        selector: str = await element.evaluate(script)
    except (PlaywrightError, AttributeError) as exc:  # pragma: no cover - defensive
        logger.debug("Failed to compute element CSS selector: %s", exc)
        return ""
    return selector


async def _best_selector(element: ElementHandle, tag: str | None = None) -> str:
    """Return the best available selector for an element.

    This coroutine first attempts the cheap, heuristic-based selection via
    ``_fast_element_selector``. If that returns a non-empty result, it is
    returned. Otherwise the function falls back to the more expensive DOM
    traversal implemented by ``_element_css_selector``.

    Always returns a string (empty string only on unexpected failures).
    """
    try:
        fast = await _fast_element_selector(element, tag=tag)
    except PlaywrightError:
        fast = None
    if fast:
        return fast
    try:
        css = await _element_css_selector(element)
    except PlaywrightError:
        css = ""
    return css or ""


async def _extract_elements(page: Page, link_limit: int = 20) -> list[Element]:
    """Extract interesting interactive elements (anchors, forms) from the page.

    Anchor collection limited to ``link_limit`` for brevity. Forms are all included.
    """
    elements: list[Element] = []

    # Buttons (including elements with role=button)
    try:
        buttons = await page.query_selector_all("button, [role=button]")
    except PlaywrightError:  # pragma: no cover - defensive
        buttons = None
    if buttons:
        for idx, b in enumerate(buttons, start=1):
            try:
                raw_text = await b.inner_text()
            except PlaywrightError as exc:  # pragma: no cover - defensive
                logger.debug("Skipping button due to error: %s", exc)
                continue
            text = (raw_text or "").strip()
            if not text:
                # Fallback to a short synthetic structural label
                text = f"Button #{idx}"
            truncated = False
            if len(text) > MAX_ELEMENT_TEXT_LEN:
                text = text[:MAX_ELEMENT_TEXT_LEN]
                truncated = True
            if truncated:
                text = text + " (truncated)"

            # Selector via centralized best-selector helper
            css_selector = await _best_selector(b, tag="button")
            try:
                role_val = await b.get_attribute("role")
            except PlaywrightError:  # pragma: no cover - defensive
                role_val = None

            elements.append(
                Element(
                    text=text,
                    role=role_val,
                    selector=css_selector,
                    tag="button",
                )
            )

    # Anchors
    try:
        anchors = await page.query_selector_all("a")
    except PlaywrightError:  # pragma: no cover - defensive
        anchors = None
    if anchors:
        for a in anchors[:link_limit]:
            try:
                raw_text = await a.inner_text()
                href_val = await a.get_attribute("href")
            except PlaywrightError as exc:  # pragma: no cover - defensive
                logger.debug("Skipping anchor due to error: %s", exc)
                continue
            text = (raw_text or "").strip()
            href = href_val or ""
            if not text or not href:
                continue
            truncated = False
            if len(text) > MAX_ELEMENT_TEXT_LEN:
                text = text[:MAX_ELEMENT_TEXT_LEN]
                truncated = True
            if truncated:
                text = text + " (truncated)"
            # Centralized selector selection (fast then fallback)
            css_selector = await _best_selector(a, tag="a")
            try:
                role_val = await a.get_attribute("role")
            except PlaywrightError:  # pragma: no cover - defensive
                role_val = None
            elements.append(
                Element(
                    text=text,
                    role=role_val,
                    selector=css_selector,
                    tag="a",
                    href=href,
                )
            )

    # Iframes
    try:
        iframes = await page.query_selector_all("iframe")
    except PlaywrightError:  # pragma: no cover - defensive
        iframes = None
    if iframes:
        from urllib.parse import urlparse

        for iframe in iframes:
            try:
                title_val = await iframe.get_attribute("title")
                src_val = await iframe.get_attribute("src")
            except PlaywrightError:  # pragma: no cover - defensive
                logger.debug("Skipping iframe due to attribute read error")
                continue

            src = src_val or ""
            # Prefer title attribute for human readable text
            text = (title_val or "").strip()
            if not text:
                # Synthesize concise label from src hostname when possible
                hostname = ""
                try:
                    hostname = urlparse(src).hostname or ""
                except (ValueError, AttributeError):
                    hostname = ""
                text = f"iframe ⇒ {hostname}" if hostname else "iframe"

            truncated = False
            if len(text) > MAX_ELEMENT_TEXT_LEN:
                text = text[:MAX_ELEMENT_TEXT_LEN]
                truncated = True
            if truncated:
                text = text + " (truncated)"

            css_selector = await _best_selector(iframe, tag="iframe")

            elements.append(
                Element(
                    text=text,
                    role=None,
                    selector=css_selector,
                    tag="iframe",
                    src=src or None,
                )
            )

    # Forms
    try:
        form_elements = await page.query_selector_all("form")
    except PlaywrightError:  # pragma: no cover - defensive
        form_elements = None
    if form_elements:
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

            # Collect detailed form fields
            form_fields: list[FormField] = []
            try:
                controls = await form_el.query_selector_all("input, textarea, select")
                for control in controls:
                    try:
                        tag = await control.evaluate("(el) => el.tagName.toLowerCase()")
                    except PlaywrightError:  # pragma: no cover - defensive
                        continue

                    try:
                        name_attr = await control.get_attribute("name")
                    except PlaywrightError:
                        name_attr = None

                    # Determine type: for inputs use type attribute, otherwise tag
                    field_type: str
                    if tag == "input":
                        try:
                            input_type = await control.get_attribute("type")
                        except PlaywrightError:
                            input_type = None
                        input_type = (input_type or "text").lower()
                        # Skip hidden/submit-like controls
                        if input_type in {"hidden", "submit", "button", "image", "reset", "file"}:
                            continue
                        field_type = input_type
                    else:
                        field_type = tag

                    try:
                        placeholder = await control.get_attribute("placeholder")
                    except PlaywrightError:
                        placeholder = None

                    try:
                        required_attr = await control.get_attribute("required")
                    except PlaywrightError:
                        required_attr = None
                    required = required_attr is not None

                    # Best selector for the control
                    control_selector = await _best_selector(control, tag=tag)

                    options_val: list[dict] | None = None
                    if tag == "select":
                        # enumerate options with visible text/value
                        try:
                            option_handles = await control.query_selector_all("option")
                        except PlaywrightError:
                            option_handles = []
                        opts: list[dict] = []
                        for opt in option_handles:
                            try:
                                val = await opt.get_attribute("value")
                                label = await opt.inner_text()
                                opts.append({"value": val or "", "label": (label or "").strip()})
                            except PlaywrightError:
                                continue
                        options_val = opts or None

                    form_fields.append(
                        FormField(
                            selector=control_selector or "",
                            name=name_attr,
                            field_type=field_type,
                            placeholder=placeholder,
                            required=required,
                            options=options_val,
                        )
                    )
            except PlaywrightError:  # pragma: no cover - defensive
                form_fields = []

            # Centralized selector selection for forms
            css_selector = await _best_selector(form_el, tag="form")
            if not css_selector:
                # if DOM-walk failed, fall back to our logical selector
                css_selector = selector

            elements.append(
                Element(
                    text=selector,  # using selector as a readable label for the form
                    role=None,
                    selector=css_selector or selector,
                    tag="form",
                    fields=form_fields or None,
                    action=action,
                )
            )

    return elements


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

    elements = await _extract_elements(page)

    return PageSnapshot(
        title=title,
        url=final_url,
        snippet=snippet,
        elements=elements,
        status_code=status_code,
    )


__all__ = ["Element", "FormField", "PageSnapshot", "_build_page_snapshot"]
