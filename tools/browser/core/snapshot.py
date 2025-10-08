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
from collections import Counter

from playwright.async_api import ElementHandle, Page, Response
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

from tools.browser.core._dom_utils import _element_bool_state

logger = logging.getLogger(__name__)

# Debug dump controls: enabled unconditionally (rate-limited) for local debugging.
_EVAL_DEBUG_ENABLED = True

# Simple rate limiter for debug dumps in this process (avoid noisy logs).
_EVAL_DEBUG_COUNT = 0
_EVAL_DEBUG_LIMIT = 10

MAX_ELEMENT_TEXT_LEN = 120
MAX_ARIA_LABEL_LEN = 40
MAX_TEXT_SELECTOR_LEN = 60


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
        "function(el){"
        "try {"
        "  if (!el || !(el instanceof Element)) return '';"
        "  var segments = [];"
        "  var current = el;"
        "  while (current && current.nodeType === Node.ELEMENT_NODE) {"
        "    var seg = current.nodeName.toLowerCase();"
        "    if (current.id) {"
        "      segments.unshift('#' + current.id);"
        "      break;"
        "    } else {"
        "      var nth = 1; var sib = current;"
        "      while ((sib = sib.previousElementSibling)) {"
        "        if (sib.nodeName === current.nodeName) nth++;"
        "      }"
        "      if (nth > 1) { seg += ':nth-of-type(' + nth + ')'; }"
        "    }"
        "    segments.unshift(seg);"
        "    current = current.parentElement;"
        "  }"
        "  return segments.join(' > ');"
        "} catch (e) { return ''; }"
        "}"
    )
    try:
        selector: str = await element.evaluate(script)
    except (PlaywrightError, AttributeError) as exc:  # pragma: no cover - defensive
        # Some Playwright environments surface JS SyntaxError as "Unexpected end of input"
        # when a script is malformed or truncated.
        msg = str(exc)
        logger.debug("Element.evaluate failed: %s", msg)

        # Log a short preview of the script so we can see if it looks truncated
        # or contains suspicious characters. If debug is enabled, emit a small
        # safe-element dump (rate-limited) underneath to help correlate the
        # failing element without dumping massive HTML.
        logger.debug(
            "Element.evaluate failed; script_len=%d script_preview=%s...%s",
            len(script),
            script[:60],
            script[-60:],
        )

        global _EVAL_DEBUG_COUNT
        if _EVAL_DEBUG_ENABLED and _EVAL_DEBUG_COUNT < _EVAL_DEBUG_LIMIT:
            try:
                _EVAL_DEBUG_COUNT += 1
                try:
                    tag = await element.evaluate("(el)=>el.tagName.toLowerCase()")
                except (PlaywrightError, AttributeError):
                    tag = None
                try:
                    eid = await element.evaluate("(el)=>el.id || null")
                except (PlaywrightError, AttributeError):
                    eid = None
                try:
                    classes = await element.evaluate("(el)=>Array.from(el.classList).slice(0,3)")
                except (PlaywrightError, AttributeError):
                    classes = None
                try:
                    outer = await element.evaluate(
                        "(el)=>{const s=el.outerHTML||'';return s.length>200?s.slice(0,200)+'...':s}"
                    )
                except (PlaywrightError, AttributeError):
                    outer = None

                logger.debug(
                    "Eval debug dump (preview) tag=%s id=%s classes=%s outer_snippet=%s",
                    tag,
                    eid,
                    classes,
                    outer,
                )
            except (PlaywrightError, AttributeError):
                pass

        # If we can't evaluate the main script, give up and return empty selector.
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


def _normalize_visible_text(value: str) -> str:
    """Normalize visible text for uniqueness comparisons."""
    if not value:
        return ""
    return " ".join(value.split()).strip().lower()


async def _resolve_element_selector(
    element: ElementHandle,
    *,
    tag: str | None,
    text: str,
    text_unique: bool,
) -> str:
    """Return the most succinct selector to expose in snapshots.

    Resolution order:
    1. ``_fast_element_selector`` (ids, data-test ids, form/action, etc.).
    2. If ``text_unique`` is True and the text is short enough, emit a
       Playwright ``text="..."`` selector so the agent sees the human label.
    3. Fall back to ``_best_selector`` which ultimately uses
       ``_element_css_selector`` to produce a stable CSS path.

    The goal is to surface the easiest-to-reuse selector for the agent, even if
    that means mixing CSS and Playwright text selectors.
    """
    try:
        fast = await _fast_element_selector(element, tag=tag)
    except PlaywrightError:
        fast = None
    if fast:
        return fast

    normalized_text = text.strip()
    if text_unique and normalized_text and len(normalized_text) <= MAX_TEXT_SELECTOR_LEN:
        escaped = normalized_text.replace('"', '\\"')
        return f'text="{escaped}"'

    try:
        css = await _element_css_selector(element)
    except PlaywrightError:
        css = ""
    if css:
        return css

    if normalized_text:
        escaped = normalized_text.replace('"', '\\"')
        return f'text="{escaped}"'

    return ""


async def _collect_anchors(page: Page) -> list[Element]:
    """Collect anchor elements from the page and return a list of Element models.

    This helper encapsulates the anchor extraction logic previously in
    ``_extract_elements`` so it can be reused (for pagination, listing, etc.).

    Args:
        page: Playwright Page to query anchors from.
        limit: Optional maximum number of anchors to consider (apply before
            selector disambiguation). When ``None``, all anchors are processed.

    Returns:
        List of ``Element`` instances for anchors found on the page.
    """
    results: list[Element] = []
    try:
        anchors = await page.query_selector_all("a")
    except PlaywrightError:  # pragma: no cover - defensive
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
        except PlaywrightError:  # pragma: no cover - defensive
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
        except PlaywrightError:  # pragma: no cover - defensive
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

    anchor_counts = Counter(entry["normalized"] for entry in anchor_data if entry["normalized"])

    for entry in anchor_data:
        text_unique = bool(entry["normalized"]) and anchor_counts[entry["normalized"]] == 1
        selector_value = await _resolve_element_selector(
            entry["handle"],
            tag="a",
            text=entry["raw"],
            text_unique=text_unique,
        )
        if not selector_value:
            selector_value = await _best_selector(entry["handle"], tag="a")
        entry["selector"] = selector_value

    anchor_selector_counts = Counter(entry.get("selector") for entry in anchor_data if entry.get("selector"))

    duplicate_anchor_keys: set[str] = {key for key, count in anchor_selector_counts.items() if key and count > 1}
    if duplicate_anchor_keys:
        # initialize per-key usage counters with correct typing
        anchor_usage: dict[str, int] = dict.fromkeys(duplicate_anchor_keys, 0)
        for entry in anchor_data:
            key = entry.get("selector", "")
            if key in duplicate_anchor_keys:
                idx = anchor_usage[key]
                entry["selector"] = f"{key} >> nth={idx}"
                anchor_usage[key] = idx + 1

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


async def _dedupe_entry_selectors(entries: list[dict], selector_key: str = "selector") -> None:
    """Local (category-level) selector disambiguation for raw mapping entries.

    Adds ``>> nth=`` suffixes when duplicates appear within the provided entries.
    This is used by individual collectors prior to constructing ``Element`` models.
    Global uniqueness (across categories) is enforced later by ``_dedupe_selectors``.
    """
    selector_counts = Counter(e.get(selector_key) for e in entries if e.get(selector_key))
    duplicate_keys: set[str] = {k for k, c in selector_counts.items() if k and c > 1}
    if not duplicate_keys:
        return
    usage: dict[str, int] = dict.fromkeys(duplicate_keys, 0)
    for e in entries:
        key = e.get(selector_key, "")
        if key in duplicate_keys:
            idx = usage[key]
            e[selector_key] = f"{key} >> nth={idx}"
            usage[key] = idx + 1


def _dedupe_selectors(elements: list[Element]) -> None:
    """Ensure global uniqueness of selectors across all element categories.

    Applies a stable pass over the combined ``elements`` list, appending
    ``>> nth={i}`` to subsequent occurrences of any non-empty selector. This
    runs after category collection so that relative ordering (buttons vs.
    anchors vs. forms) is preserved in the final suffixed sequence.
    Tests covering cross-category collisions: ``test_snapshot_dedup_selectors``.
    """
    usage: dict[str, int] = {}
    for el in elements:
        sel = el.selector
        if not sel:
            continue
        count = usage.get(sel)
        if count is None:
            # first occurrence: record next duplicate index starting at 0
            usage[sel] = 0
            continue
        # duplicate occurrence: use current count value, then increment
        el.selector = f"{sel} >> nth={count}"
        usage[sel] = count + 1


async def _collect_buttons(page: Page) -> list[Element]:
    """Collect button-like elements (button tag + role=button)."""
    try:
        handles = await page.query_selector_all("button, [role=button]")
    except PlaywrightError:  # pragma: no cover - defensive
        handles = None
    if not handles:
        return []
    data: list[dict] = []
    for idx, h in enumerate(handles, start=1):
        # Call ``is_visible`` directly; test doubles must supply it.
        try:
            is_visible = await h.is_visible()
        except PlaywrightError:  # pragma: no cover - defensive
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
        except PlaywrightError:  # pragma: no cover - defensive
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
    counts = Counter(d["normalized"] for d in data if d["normalized"])
    for d in data:
        text_unique = bool(d["normalized"]) and counts[d["normalized"]] == 1
        selector_value = await _resolve_element_selector(
            d["handle"],
            tag="button",
            text=d["raw"],
            text_unique=text_unique,
        )
        if not selector_value:
            selector_value = await _best_selector(d["handle"], tag="button")
        d["selector"] = selector_value
    await _dedupe_entry_selectors(data)
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


async def _collect_iframes(page: Page) -> list[Element]:
    """Collect iframe elements with synthesized readable labels."""
    try:
        iframes = await page.query_selector_all("iframe")
    except PlaywrightError:  # pragma: no cover - defensive
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
        css_selector = await _best_selector(iframe, tag="iframe")
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


async def _collect_forms(page: Page) -> list[Element]:
    """Collect form elements and their fields (logic extracted from _extract_elements)."""
    try:
        form_elements = await page.query_selector_all("form")
    except PlaywrightError:  # pragma: no cover - defensive
        form_elements = None
    if not form_elements:
        return []
    seen_global_selectors: set[str] = set()
    results: list[Element] = []
    for idx, form_el in enumerate(form_elements, start=1):
        field_selectors_seen: set[str] = set()
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
        locator = await _resolve_element_selector(
            form_el,
            tag="form",
            text="",
            text_unique=False,
        )
        effective_selector = locator or selector
        form_fields: list[FormField] = []
        radio_selector_counters: dict[str, int] = {}
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
                if field_type == "radio" and name_attr:
                    idx_counter = radio_selector_counters.get(name_attr, 0)
                    control_selector = f"input[type='radio'][name='{name_attr}'] >> nth={idx_counter}"
                    radio_selector_counters[name_attr] = idx_counter + 1
                    try:
                        raw_val = await control.get_attribute("value")
                    except PlaywrightError as exc:
                        logger.debug(
                            "Radio value attribute read failed for name=%s index=%s: %s",
                            name_attr,
                            idx_counter,
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
                else:
                    control_selector = await _resolve_element_selector(
                        control,
                        tag=tag,
                        text="",
                        text_unique=False,
                    )
                    if (
                        not control_selector
                        or control_selector in field_selectors_seen
                        or control_selector in seen_global_selectors
                    ):
                        try:
                            css_fallback = await _element_css_selector(control)
                        except PlaywrightError:
                            css_fallback = ""
                        control_selector = css_fallback or control_selector
                    if name_attr and (action or form_id):
                        try:
                            scoped_css = await _element_css_selector(control)
                        except PlaywrightError:
                            scoped_css = ""
                        if scoped_css:
                            control_selector = scoped_css
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
                if control_selector and (
                    control_selector in field_selectors_seen or control_selector in seen_global_selectors
                ):
                    base_selector = control_selector
                    suffix = 0
                    while control_selector in field_selectors_seen or control_selector in seen_global_selectors:
                        control_selector = f"{base_selector} >> nth={suffix}"
                        suffix += 1
                if control_selector:
                    field_selectors_seen.add(control_selector)
                    seen_global_selectors.add(control_selector)
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
        except PlaywrightError:
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


async def _collect_clickables(page: Page, *, limit: int | None = None) -> list[Element]:
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
        limit: Optional maximum number of clickables to return.

    Returns:
        List of ``Element`` entries describing heuristic clickables.
    """
    selectors = [
        "div[onclick]",
        "span[onclick]",
        "li[onclick]",
        "[role='button']",
        "[role='link']",
        "[tabindex]",
        "[data-clickable]",
    ]
    # Join with commas to issue one DOM query; Playwright returns in document order.
    query = ", ".join(selectors)
    try:
        handles = await page.query_selector_all(query)
    except (PlaywrightError, AssertionError) as exc:  # pragma: no cover - defensive
        # Older test fakes raise AssertionError for unknown selectors; treat as no clickables.
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
        except PlaywrightError:
            continue
        if tag_name in {"a", "button", "input", "select", "textarea", "form", "iframe"}:
            continue
        # Visibility heuristic
        try:
            is_visible = await h.is_visible()
        except PlaywrightError:
            is_visible = False
        if not is_visible:
            continue
        # Removed extra hidden heuristic to avoid false negatives; rely solely on Playwright's is_visible().
        # Text / labeling
        try:
            raw_text = await h.inner_text()
        except PlaywrightError:
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
        except PlaywrightError:
            role_val = None
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
    counts = Counter(d["normalized"] for d in processed if d["normalized"])
    for d in processed:
        text_unique = bool(d["normalized"]) and counts[d["normalized"]] == 1
        selector_value = await _resolve_element_selector(
            d["handle"],
            tag=d["tag"],
            text=d["raw"],
            text_unique=text_unique,
        )
        if not selector_value:
            selector_value = await _best_selector(d["handle"], tag=d["tag"])
        d["selector"] = selector_value
    await _dedupe_entry_selectors(processed)
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


async def _extract_elements(page: Page, link_limit: int = 20) -> list[Element]:
    """Extract interactive elements orchestrating specialized helpers.

    Ordering preserved (with clickables inserted after buttons) for backward compatibility:
        1. Buttons
        2. Clickables (new heuristic non-semantic interactive elements)
        3. Anchors (limited by link_limit)
        4. Iframes
        5. Forms

    Clickables are conservatively selected to avoid flooding snapshots.
    """
    elements: list[Element] = []
    # Collect full sets (no limiting yet, anchor/button/clickable counts small enough)
    button_elements = await _collect_buttons(page)
    clickable_elements = await _collect_clickables(page, limit=link_limit)  # still locally limited
    anchor_elements_full = await _collect_anchors(page)
    iframe_elements = await _collect_iframes(page)
    form_elements = await _collect_forms(page)

    elements.extend(button_elements)
    elements.extend(clickable_elements)
    elements.extend(anchor_elements_full)
    elements.extend(iframe_elements)
    elements.extend(form_elements)

    # Global dedupe across categories before slicing anchors for link limit.
    _dedupe_selectors(elements)

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
