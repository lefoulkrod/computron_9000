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

from tools.browser.core._dom_utils import _element_bool_state
from tools.browser.core.selectors import SelectorRegistry, build_unique_selector

logger = logging.getLogger(__name__)

# Debug dump controls: enabled unconditionally (rate-limited) for local debugging.
_EVAL_DEBUG_ENABLED = True

# Simple rate limiter for debug dumps in this process (avoid noisy logs).
_EVAL_DEBUG_COUNT = 0
_EVAL_DEBUG_LIMIT = 10

MAX_ELEMENT_TEXT_LEN = 120
MAX_ARIA_LABEL_LEN = 40
MAX_TEXT_SELECTOR_LEN = 60


class Element(BaseModel):
    """Generic element returned in a page snapshot.

    Attributes:
        text: Visible text for the element (may end with " (truncated)" if clipped).
        role: Optional ARIA role string when present on the element.
        selector: A selector handle that can be used to interact with the element.
        tag: The element tag name (for example "a", "button", "form", "iframe").
        href: For anchors, the href value when present.
        fields: For forms, a list of `FormField` entries describing controls contained in the form.
        action: For forms, the form's action attribute when present.
        src: For iframes, the src attribute when present.
    """

    text: str = Field(..., max_length=140)
    role: str | None = None
    selector: str
    tag: str
    href: str | None = None
    fields: list[FormField] | None = None
    action: str | None = None
    src: str | None = None


class FormField(BaseModel):
    """Metadata for a single form control within a form element.

    Attributes:
        selector: CSS or Playwright selector string that targets the control.
        name: ``name`` attribute value when present.
        field_type: Control type (input ``type`` or tag name).
        placeholder: ``placeholder`` attribute value when present.
        required: Whether the control has the ``required`` attribute.
        value: Current ``value`` attribute for inputs/textareas/selects (empty string
            allowed). Not populated for types where reading value is non-trivial (e.g. file).
        selected: For checkbox/radio, whether the control is currently selected/checked.
            For other field types this remains False.
        options: For select elements, a list of option descriptors with ``value``, ``label`` and
            ``selected`` flags indicating which options are currently chosen (multi-select may
            have multiple selected).
    """

    selector: str
    name: str | None = None
    field_type: str
    placeholder: str | None = None
    required: bool = False
    value: str | None = None
    selected: bool = False
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


def _normalize_visible_text(value: str) -> str:
    """Normalize visible text for uniqueness comparisons."""
    if not value:
        return ""
    return " ".join(value.split()).strip().lower()


async def _collect_anchors(page: Page, registry: SelectorRegistry) -> list[Element]:
    """Collect anchor elements from the page and return a list of Element models.

    This helper encapsulates the anchor extraction logic previously in
    ``_extract_elements`` so it can be reused (for pagination, listing, etc.).

    Args:
        page: Playwright Page to query anchors from.
        registry: SelectorRegistry instance used to build unique selectors for anchors.
        limit: Optional maximum number of anchors to consider (apply before
            selector disambiguation). When ``None``, all anchors are processed.

    Returns:
        List of ``Element`` instances for anchors found on the page.
    """
    results: list[Element] = []
    try:
        anchors = await page.query_selector_all("a")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Anchor query failed, defaulting to no anchors: %s", exc)
        anchors = None
    if not anchors:
        return results

    anchor_handles = anchors
    anchor_data: list[dict] = []
    for a in anchor_handles:
        # Rely on Playwright-compatible protocol: test doubles must implement
        # ``is_visible`` to participate. This keeps production code simple and
        # avoids dynamic hasattr checks.
        try:
            is_visible = await a.is_visible()
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Anchor visibility check failed, treating as not visible: %s", exc)
            is_visible = False
        except AttributeError:  # pragma: no cover - defensive
            # Test double missing attribute: treat as not visible so tests
            # surface the issue explicitly rather than silently succeeding.
            is_visible = False
        if not is_visible:
            continue
        try:
            raw_text = await a.inner_text()
            href_val = await a.get_attribute("href")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Skipping anchor due to error: %s", exc)
            continue
        trimmed_text = (raw_text or "").strip()
        href = href_val or ""
        if not trimmed_text or not href:
            continue
        display_text = trimmed_text
        truncated = False
        if len(display_text) > MAX_ELEMENT_TEXT_LEN:
            display_text = display_text[:MAX_ELEMENT_TEXT_LEN]
            truncated = True
        if truncated:
            display_text = display_text + " (truncated)"
        try:
            role_val = await a.get_attribute("role")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to read anchor role attribute, defaulting to None: %s", exc)
            role_val = None

        anchor_data.append(
            {
                "handle": a,
                "display": display_text,
                "raw": trimmed_text,
                "normalized": _normalize_visible_text(trimmed_text),
                "role": role_val,
                "href": href,
                "tag": "a",
            }
        )

    # anchor_counts was previously used for de-duplication; registry handles uniqueness now

    for entry in anchor_data:
        # Prefer registry-driven unique selector generation. Pass the visible raw text
        # so the registry can consider text-based strategies when appropriate.
        try:
            sel_res = await build_unique_selector(entry["handle"], tag="a", text=entry["raw"], registry=registry)
            entry["selector"] = sel_res.selector
        except Exception as exc:
            logger.exception("SelectorRegistry failed while building anchor selector: %s", exc)
            # Per new contract: do not fall back to legacy helpers. Emit empty selector.
            entry["selector"] = ""

    # Selector uniqueness and any necessary disambiguation is handled by
    # SelectorRegistry.register. Do not perform local deduplication here.

    for entry in anchor_data:
        results.append(
            Element(
                text=entry["display"],
                role=entry["role"],
                selector=entry.get("selector", ""),
                tag="a",
                href=entry["href"],
            )
        )

    return results


async def _collect_buttons(page: Page, registry: SelectorRegistry) -> list[Element]:
    """Collect button-like elements (button tag + role=button)."""
    try:
        handles = await page.query_selector_all("button, [role=button]")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Button query failed, defaulting to no buttons: %s", exc)
        handles = None
    if not handles:
        return []
    data: list[dict] = []
    for idx, h in enumerate(handles, start=1):
        # Call ``is_visible`` directly; test doubles must supply it.
        try:
            is_visible = await h.is_visible()
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Button visibility check failed, treating as not visible: %s", exc)
            is_visible = False
        except AttributeError:  # pragma: no cover - defensive
            is_visible = False
        if not is_visible:
            continue
        try:
            raw_text = await h.inner_text()
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Skipping button due to error: %s", exc)
            continue
        trimmed = (raw_text or "").strip()
        display = trimmed or f"Button #{idx}"
        truncated = False
        if len(display) > MAX_ELEMENT_TEXT_LEN:
            display = display[:MAX_ELEMENT_TEXT_LEN]
            truncated = True
        if truncated:
            display = display + " (truncated)"
        try:
            role_val = await h.get_attribute("role")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to read button role attribute, defaulting to None: %s", exc)
            role_val = None
        data.append(
            {
                "handle": h,
                "display": display,
                "raw": trimmed,
                "normalized": _normalize_visible_text(trimmed),
                "role": role_val,
                "tag": "button",
            }
        )
    # category-level counts intentionally unused; registry provides uniqueness
    for d in data:
        try:
            sel_res = await build_unique_selector(d["handle"], tag="button", text=d["raw"], registry=registry)
            d["selector"] = sel_res.selector
        except Exception as exc:
            logger.exception("SelectorRegistry failed while building button selector: %s", exc)
            d["selector"] = ""
    elements: list[Element] = []
    for d in data:
        elements.append(
            Element(
                text=d["display"],
                role=d["role"],
                selector=d.get("selector", ""),
                tag="button",
            )
        )
    return elements


async def _collect_iframes(page: Page, registry: SelectorRegistry) -> list[Element]:
    """Collect iframe elements with synthesized readable labels."""
    try:
        iframes = await page.query_selector_all("iframe")
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.debug("Iframe query failed, defaulting to no iframes: %s", exc)
        iframes = None
    if not iframes:
        return []
    from urllib.parse import urlparse

    results: list[Element] = []
    for iframe in iframes:
        try:
            title_val = await iframe.get_attribute("title")
            src_val = await iframe.get_attribute("src")
        except PlaywrightError:  # pragma: no cover - defensive
            logger.debug("Skipping iframe due to attribute read error")
            continue
        src = src_val or ""
        text = (title_val or "").strip()
        if not text:
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
        try:
            sel_res = await build_unique_selector(iframe, tag="iframe", text=text, registry=registry)
            css_selector = sel_res.selector
        except Exception as exc:
            logger.exception("SelectorRegistry failed while building iframe selector: %s", exc)
            css_selector = ""
        results.append(
            Element(
                text=text,
                role=None,
                selector=css_selector,
                tag="iframe",
                src=src or None,
            )
        )
    return results


async def _collect_forms(page: Page, registry: SelectorRegistry) -> list[Element]:
    """Collect form elements and their fields (logic extracted from _extract_elements)."""
    try:
        form_elements = await page.query_selector_all("form")
    except PlaywrightError:  # pragma: no cover - defensive
        form_elements = None
    if not form_elements:
        return []
    # SelectorRegistry guarantees uniqueness across the snapshot; local
    # global selector tracking is no longer required.
    results: list[Element] = []
    for idx, form_el in enumerate(form_elements, start=1):
        # per-form selector tracking removed; SelectorRegistry guarantees uniqueness
        try:
            action = await form_el.get_attribute("action")
            form_id = await form_el.get_attribute("id")
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("Form attribute read failed, defaulting action/id to None: %s", exc)
            action = None
            form_id = None
        if action:
            selector = f"form[action='{action}']"
        elif form_id:
            selector = f"form#{form_id}"
        else:
            selector = f"form:nth-of-type({idx})"
        try:
            res = await build_unique_selector(form_el, tag="form", text="", registry=registry)
            locator = res.selector
        except Exception as exc:
            logger.exception("SelectorRegistry failed while building form selector: %s", exc)
            locator = ""
        effective_selector = locator or selector
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
                field_type: str
                if tag == "input":
                    try:
                        input_type = await control.get_attribute("type")
                    except PlaywrightError:
                        input_type = None
                    input_type = (input_type or "text").lower()
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
                options_val: list[dict] | None = None
                current_value: str | None = None
                selected_flag: bool = False
                # All controls, including radios, request a selector from
                # the centralized SelectorRegistry. If the registry fails
                # we emit an empty selector per the contract and continue
                # collecting metadata.
                try:
                    cres = await build_unique_selector(control, tag=tag, text="", registry=registry)
                    control_selector = cres.selector
                except Exception as exc:
                    logger.exception("SelectorRegistry failed while building control selector: %s", exc)
                    control_selector = ""
                if tag == "select":
                    try:
                        option_handles = await control.query_selector_all("option")
                    except PlaywrightError as exc:
                        logger.debug(
                            "Select option enumeration failed (name=%s): %s",
                            name_attr,
                            exc,
                        )
                        option_handles = []
                    opts: list[dict] = []
                    for opt in option_handles:
                        try:
                            val = await opt.get_attribute("value")
                            label = await opt.inner_text()
                            opt_selected = await _element_bool_state(
                                opt,
                                prop_script="o => o.selected === true",
                                attr="selected",
                                default=False,
                                context="select_option",
                            )
                            opts.append(
                                {
                                    "value": val or "",
                                    "label": (label or "").strip(),
                                    "selected": opt_selected,
                                }
                            )
                            if opt_selected and current_value is None:
                                current_value = val or ""
                        except PlaywrightError as exc:
                            logger.debug(
                                "Select option processing failed (name=%s): %s",
                                name_attr,
                                exc,
                            )
                            continue
                    options_val = opts or None
                    if current_value is None and opts:
                        current_value = opts[0]["value"]
                elif field_type == "radio":
                    try:
                        raw_val = await control.get_attribute("value")
                    except PlaywrightError as exc:
                        logger.debug(
                            "Radio value attribute read failed for name=%s: %s",
                            name_attr,
                            exc,
                        )
                        raw_val = None
                    current_value = raw_val or ""
                    selected_flag = await _element_bool_state(
                        control,
                        prop_script="el => el.checked === true",
                        attr="checked",
                        default=False,
                        context="radio",
                    )
                elif field_type not in {"radio", "checkbox"}:
                    raw_val = None
                    try:
                        raw_val = await control.evaluate("el => el.value")
                    except PlaywrightError as exc:
                        logger.debug(
                            "Field value property read failed (type=%s name=%s): %s",
                            field_type,
                            name_attr,
                            exc,
                        )
                        raw_val = None
                    if raw_val is None:
                        try:
                            raw_attr = await control.get_attribute("value")
                        except PlaywrightError as exc:
                            logger.debug(
                                "Field value attribute read failed (type=%s name=%s): %s",
                                field_type,
                                name_attr,
                                exc,
                            )
                            raw_attr = None
                        raw_val = raw_attr
                    if raw_val is not None:
                        current_value = raw_val
                elif field_type == "checkbox":
                    try:
                        raw_val = await control.get_attribute("value")
                    except PlaywrightError as exc:
                        logger.debug(
                            "Checkbox value attribute read failed (name=%s): %s",
                            name_attr,
                            exc,
                        )
                        raw_val = None
                    current_value = raw_val or "on"
                    selected_flag = await _element_bool_state(
                        control,
                        prop_script="el => el.checked === true",
                        attr="checked",
                        default=False,
                        context="checkbox",
                    )
                # Per-form selector tracking removed — rely on SelectorRegistry for uniqueness.
                form_fields.append(
                    FormField(
                        selector=control_selector or "",
                        name=name_attr,
                        field_type=field_type,
                        placeholder=placeholder,
                        required=required,
                        value=current_value,
                        selected=selected_flag,
                        options=options_val,
                    )
                )
        except PlaywrightError as exc:
            logger.debug("Failed to enumerate form controls, defaulting to empty fields: %s", exc)
            form_fields = []
        css_selector = effective_selector or selector
        results.append(
            Element(
                text=selector,
                role=None,
                selector=css_selector or selector,
                tag="form",
                fields=form_fields or None,
                action=action,
            )
        )
    return results


async def _collect_clickables(page: Page, registry: SelectorRegistry, *, limit: int | None = None) -> list[Element]:
    """Collect non-semantic but interactive elements (heuristic clickables).

    Heuristics (conservative):
        * Elements with explicit interaction hooks/roles: div/span/li having any of:
            - onclick attribute
            - role="button" or role="link"
            - tabindex (focusable) without native semantic tag
            - data-clickable attribute
        * Excludes native interactive tags already captured (a, button, input, select,
          textarea, form, iframe) to avoid duplication.
        * Skips hidden elements (not visible or display:none / visibility:hidden / aria-hidden).

    Args:
        page: Playwright page.
        registry: SelectorRegistry used to generate unique selectors for handles.
        limit: Optional maximum number of clickables to return.

    Returns:
        List of ``Element`` entries describing heuristic clickables.
    """
    selectors = [
        "div[onclick]",
        "span[onclick]",
        "li[onclick]",
        "[role='link']",
        "[tabindex]",
        "[data-clickable]",
    ]
    # Join with commas to issue one DOM query; Playwright returns in document order.
    query = ", ".join(selectors)
    try:
        handles = await page.query_selector_all(query)
    except PlaywrightError as exc:
        logger.debug("Clickable query skipped due to error: %s", exc)
        handles = None
    if not handles:
        return []

    processed: list[dict] = []
    seen_element_ids: set[int] = set()
    # We will collect tag names for exclusion and labeling.
    for h in handles:
        # Handle identity to prevent duplicates if selector overlap selects same node.
        obj_id = id(h)
        if obj_id in seen_element_ids:
            continue
        seen_element_ids.add(obj_id)
        try:
            tag_name = await h.evaluate("el => el.tagName.toLowerCase()")
        except PlaywrightError as exc:
            logger.debug("Clickable tag evaluation failed, skipping element: %s", exc)
            continue
        if tag_name in {"a", "button", "input", "select", "textarea", "form", "iframe"}:
            continue
        # Visibility heuristic
        try:
            is_visible = await h.is_visible()
        except PlaywrightError as exc:
            logger.debug("Clickable visibility check failed, treating as not visible: %s", exc)
            is_visible = False
        if not is_visible:
            continue
        # Text / labeling
        try:
            raw_text = await h.inner_text()
        except PlaywrightError as exc:
            logger.debug("Clickable inner_text read failed, defaulting to empty string: %s", exc)
            raw_text = ""
        trimmed = (raw_text or "").strip()
        # Fallback label attributes
        if not trimmed:
            label_candidates = ["aria-label", "title", "data-tooltip", "data-label"]
            label_value = None
            for attr in label_candidates:
                try:
                    val = await h.get_attribute(attr)
                except PlaywrightError:
                    val = None
                if val:
                    label_value = val.strip()
                    if label_value:
                        break
            trimmed = label_value or ""
        display = trimmed
        # Placeholder label if still empty
        if not display:
            display = f"Clickable #{len(processed) + 1}"
        truncated = False
        if len(display) > MAX_ELEMENT_TEXT_LEN:
            display = display[:MAX_ELEMENT_TEXT_LEN]
            truncated = True
        if truncated:
            display = display + " (truncated)"
        try:
            role_val = await h.get_attribute("role")
        except PlaywrightError as exc:
            logger.debug("Failed to read clickable role attribute, defaulting to None: %s", exc)
            role_val = None
        if role_val and role_val.lower() == "button":
            # Already captured by button collector; skip to avoid duplicates.
            continue
        processed.append(
            {
                "handle": h,
                "display": display,
                "raw": trimmed,
                "normalized": _normalize_visible_text(trimmed),
                "role": role_val,
                "tag": tag_name,
            }
        )
        if limit is not None and len(processed) >= limit:
            break

    if not processed:
        return []
    # category-level counts intentionally unused; registry provides uniqueness
    for d in processed:
        try:
            sel_res = await build_unique_selector(d["handle"], tag=d["tag"], text=d["raw"], registry=registry)
            d["selector"] = sel_res.selector
        except Exception as exc:
            logger.exception("SelectorRegistry failed while building clickable selector: %s", exc)
            d["selector"] = ""
    # Local dedupe is no longer required since registry guarantees uniqueness.
    elements: list[Element] = []
    for d in processed:
        elements.append(
            Element(
                text=d["display"],
                role=d["role"],
                selector=d.get("selector", ""),
                tag=d["tag"],
            )
        )
    return elements


async def _extract_elements(page: Page, registry: SelectorRegistry, link_limit: int = 20) -> list[Element]:
    """Extract interactive elements orchestrating specialized helpers.

    Ordering preserved (with clickables inserted after buttons) for backward compatibility:
        1. Buttons
        2. Clickables (new heuristic non-semantic interactive elements)
        3. Anchors (limited by link_limit)
        4. Iframes
        5. Forms

    Clickables are conservatively selected to avoid flooding snapshots.
    """
    # Registry must be provided by the caller to ensure a single per-page
    # registry is used across all collectors. Do not create a registry here.
    if registry is None:  # defensive runtime check for callers still passing None
        raise ValueError("SelectorRegistry must be provided to _extract_elements")
    elements: list[Element] = []
    # Collect full sets (no limiting yet, anchor/button/clickable counts small enough)
    button_elements = await _collect_buttons(page, registry)
    clickable_elements = await _collect_clickables(page, registry, limit=link_limit)  # still locally limited
    anchor_elements_full = await _collect_anchors(page, registry)
    iframe_elements = await _collect_iframes(page, registry)
    form_elements = await _collect_forms(page, registry)

    elements.extend(button_elements)
    elements.extend(clickable_elements)
    elements.extend(anchor_elements_full)
    elements.extend(iframe_elements)
    elements.extend(form_elements)

    # Global deduplication is managed by the SelectorRegistry via unique
    # selector generation. No further cross-category post-processing is
    # required here.

    if link_limit is not None:
        # Apply limit only to anchors while keeping order & deduped selectors.
        limited: list[Element] = []
        anchor_seen = 0
        for el in elements:
            if el.tag == "a":
                if anchor_seen >= link_limit:
                    continue
                anchor_seen += 1
            limited.append(el)
        elements = limited
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
        logger.debug("Failed to read page title, defaulting to empty string")
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
        logger.debug("Failed to read body inner_text, defaulting to empty string")
        body_text = ""
    snippet = (body_text or "").strip()[:500]

    # Create a selector registry that will persist for the duration of this
    # snapshot build so selectors are globally unique across collectors.
    registry = SelectorRegistry(page)
    elements = await _extract_elements(page, registry)

    return PageSnapshot(
        title=title,
        url=final_url,
        snippet=snippet,
        elements=elements,
        status_code=status_code,
    )


__all__ = ["Element", "FormField", "PageSnapshot", "_build_page_snapshot"]
