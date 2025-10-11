"""Human-like interaction helpers for browser tools."""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from config import load_config
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


@dataclass
class _HumanConfig:
    move_steps: int
    offset_px: float
    hover_min_ms: int
    hover_max_ms: int
    click_hold_min_ms: int
    click_hold_max_ms: int
    delay_min_ms: int
    delay_max_ms: int
    extra_pause_every_chars: int
    extra_pause_min_ms: int
    extra_pause_max_ms: int


_config_cache: _HumanConfig | None = None


def _get_human_config() -> _HumanConfig:
    global _config_cache
    if _config_cache is None:
        cfg = load_config().tools.browser.human
        pointer = cfg.pointer
        typing = cfg.typing
        _config_cache = _HumanConfig(
            move_steps=max(1, pointer.move_steps),
            offset_px=max(0.0, pointer.offset_px),
            hover_min_ms=max(0, pointer.hover_min_ms),
            hover_max_ms=max(pointer.hover_min_ms, pointer.hover_max_ms),
            click_hold_min_ms=max(0, pointer.click_hold_min_ms),
            click_hold_max_ms=max(pointer.click_hold_min_ms, pointer.click_hold_max_ms),
            delay_min_ms=max(0, typing.delay_min_ms),
            delay_max_ms=max(typing.delay_min_ms, typing.delay_max_ms),
            extra_pause_every_chars=max(typing.extra_pause_every_chars, 0),
            extra_pause_min_ms=max(0, typing.extra_pause_min_ms),
            extra_pause_max_ms=max(typing.extra_pause_min_ms, typing.extra_pause_max_ms),
        )
    return _config_cache


async def _sleep_ms(duration_ms: int) -> None:
    if duration_ms <= 0:
        return
    await asyncio.sleep(duration_ms / 1000.0)


# A developer-visible, in-page faux cursor overlay to help debugging and visual
# tracing of automated mouse movements. This is strictly a cosmetic DOM element
# that does not affect the real OS pointer. Failures are intentionally ignored
# (CSP, sandboxed pages, or other restrictions) so automation continues to
# function even when the overlay cannot be installed.
_CURSOR_OVERLAY_SCRIPT = """
(() => {
    if (window.__llmCursorSet) return;
        const ring = document.createElement('div');
        ring.id = '__llm_cursor_ring__';
        ring.style.cssText = `
            position:fixed;
            width:96px;
            height:96px;
            border:8px solid #fff;
            border-radius:50%;
            background:rgba(0,0,0,0.35);
            box-shadow:0 0 18px rgba(0,0,0,0.45);
            pointer-events:none;
            z-index:2147483647;
            left:-9999px;
            top:-9999px;
            transform:translate(-50%,-50%);
            transition:left 90ms ease-out, top 90ms ease-out;
        `;
        const dot = document.createElement('div');
        dot.id = '__llm_cursor_dot__';
        dot.style.cssText = `
            position:fixed;
            width:16px;
            height:16px;
            border-radius:50%;
            background:rgba(255,60,60,0.95);
            box-shadow:0 0 8px rgba(255,60,60,0.9);
            pointer-events:none;
            z-index:2147483648;
            left:-9999px;
            top:-9999px;
            transform:translate(-50%,-50%);
        `;
        document.body.appendChild(ring);
        document.body.appendChild(dot);
    // Store last set position so move helpers can read it and animate from there.
        window.__llmCursorPos = [-9999, -9999];
        window.__llmCursorSet = (x, y) => {
            ring.style.left = x + 'px';
            ring.style.top = y + 'px';
            dot.style.left = x + 'px';
            dot.style.top = y + 'px';
            window.__llmCursorPos = [x, y];
        };
    window.__llmCursorGet = () => window.__llmCursorPos;
})();
"""


async def _ensure_cursor_overlay(page: Page) -> None:
    """Try to install the in-page visual cursor overlay.

    This swallows exceptions; failures shouldn't break interaction flows.
    """
    # Best-effort only; ignore failures so clicks/typing proceed. Log outcome
    try:
        await page.evaluate(_CURSOR_OVERLAY_SCRIPT)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to inject fake cursor overlay on page %s; proceeding without overlay. Error: %s",
            getattr(page, "url", "<unknown>"),
            exc,
        )

    # Check presence (best-effort) and log whether overlay is available. If
    # presence cannot be checked, assume unavailable and continue.
    installed = False
    try:
        installed = await page.evaluate("() => !!window.__llmCursorSet")
    except PlaywrightError as exc:
        logger.warning(
            "Failed to check cursor overlay presence on page %s; assuming overlay is unavailable. Error: %s",
            getattr(page, "url", "<unknown>"),
            exc,
        )
    if installed:
        logger.debug("Injected fake cursor overlay into page %s", getattr(page, "url", "<unknown>"))
    else:
        logger.debug("Fake cursor overlay not present on page %s", getattr(page, "url", "<unknown>"))


async def _mouse_move_with_fake_cursor(page: Page, *, x: float, y: float, steps: int) -> None:
    """Move the Playwright mouse while updating the in-page fake cursor overlay.

    This is a small wrapper that ensures the overlay exists and is updated
    (best-effort) before delegating to Playwright's mouse.move.
    """
    await _ensure_cursor_overlay(page)

    # Try to read the overlay's last-known position so we can animate from it.
    start_x = x
    start_y = y
    try:
        pos = await page.evaluate("() => window.__llmCursorGet ? window.__llmCursorGet() : null")
        if isinstance(pos, list) and len(pos) == 2:
            try:
                sx = float(pos[0])
                sy = float(pos[1])
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Invalid fake cursor position values %s on page %s; using target coordinates as default. Error: %s",
                    pos,
                    getattr(page, "url", "<unknown>"),
                    exc,
                )
                sx = x
                sy = y
            # If the stored position is the sentinel off-screen value, treat as unset.
            if not (math.isfinite(sx) and math.isfinite(sy)) or (sx == -9999 and sy == -9999):
                logger.warning(
                    "Fake cursor position is unset or non-finite on page %s; using target coordinates as default.",
                    getattr(page, "url", "<unknown>"),
                )
                sx = x
                sy = y
            start_x, start_y = sx, sy
    except PlaywrightError as exc:
        logger.warning(
            "Failed to read fake cursor position on page %s; using target coordinates as default. Error: %s",
            getattr(page, "url", "<unknown>"),
            exc,
        )

    # Animate the overlay and move the real mouse in small increments so the
    # in-page fake cursor visibly follows the pointer during movement.
    steps_count = max(1, int(steps))
    for step_idx in range(1, steps_count + 1):
        t = step_idx / steps_count
        xi = start_x + (x - start_x) * t
        yi = start_y + (y - start_y) * t
        try:
            await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [xi, yi])
        except PlaywrightError as exc:
            logger.warning(
                (
                    "Failed to update fake cursor overlay at (%s, %s) on page %s; "
                    "continuing without overlay update. Error: %s"
                ),
                xi,
                yi,
                getattr(page, "url", "<unknown>"),
                exc,
            )
        # Move the real mouse a small step; using steps=1 keeps movement discrete
        # and lets us control the overlay per-step.
        await page.mouse.move(xi, yi, steps=1)
        # Small pause to let the browser render the overlay movement. Keep this
        # brief to avoid slowing tests too much while still producing visible motion.
        await asyncio.sleep(0.03)


async def human_click(page: Page, locator: Locator) -> None:
    """Perform a human-like click on an element using an explicit Playwright page.

    Args:
        page: Playwright Page object whose mouse will be used to perform the click.
        locator: Locator identifying the element to click.

    Raises:
        BrowserToolError: If the locator cannot be resolved or the page lacks a mouse.
    """
    cfg = _get_human_config()
    handle = await locator.element_handle()
    if handle is None:
        raise BrowserToolError("Unable to resolve element handle", tool="click")
    # The element must be attached to a frame/page. Using the page's mouse
    # requires a real frame with render coordinates; previously we fell back
    # to ``locator.click()`` for test doubles or detached handles. That
    # accommodation has been removed from production code. Callers must
    # ensure the element is attached to the document of the provided page.
    frame = await handle.owner_frame()
    if frame is None:
        raise BrowserToolError(
            "Element is not attached to a frame/page; cannot perform mouse-based click",
            tool="click",
        )

    box = await handle.bounding_box()
    if box is None or box.get("width", 0) < 4 or box.get("height", 0) < 4:
        label_handle = await handle.evaluate_handle("(el) => el.labels?.[0] ?? null")
        try:
            label_element = label_handle.as_element()
            if label_element is not None:
                label_box = await label_element.bounding_box()
                if label_box and label_box.get("width", 0) >= 4 and label_box.get("height", 0) >= 4:
                    box = label_box
        finally:
            await label_handle.dispose()

    if box is None or box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
        # No usable bounding box; the caller should ensure a visible element selector.
        raise BrowserToolError("Element has no bounding box to click", tool="click")

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="click")

    target_x = box["x"] + box["width"] / 2
    target_y = box["y"] + box["height"] / 2

    if cfg.offset_px > 0:
        angle = random.random() * 2 * math.pi
        radius = random.random() * cfg.offset_px
        target_x += math.cos(angle) * radius
        target_y += math.sin(angle) * radius

    mouse = page.mouse
    # Use the mouse-move wrapper which also updates the visual overlay.
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y, steps=cfg.move_steps)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await mouse.up()
    # Ensure overlay is finally positioned on the click point (best-effort).
    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [target_x, target_y])
    except PlaywrightError as exc:
        logger.warning(
            (
                "Failed to finalize fake cursor overlay at click point (%s, %s) on page %s; "
                "continuing without overlay update. Error: %s"
            ),
            target_x,
            target_y,
            getattr(page, "url", "<unknown>"),
            exc,
        )


async def human_drag(
    page: Page,
    source_locator: Locator,
    *,
    target_locator: Locator | None = None,
    offset: tuple[float | int, float | int] | None = None,
) -> None:
    """Drag from ``source_locator`` to either ``target_locator`` or a coordinate offset.

    Exactly one of ``target_locator`` or ``offset`` must be provided.

    Args:
        page: Playwright Page whose mouse will be used for the drag.
        source_locator: Locator identifying the element where the drag should begin.
        target_locator: Optional locator identifying the destination element.
        offset: Optional ``(dx, dy)`` tuple specifying a pixel offset relative to the
            drag start point.

    Raises:
        BrowserToolError: On invalid inputs, detached elements, missing mouse APIs,
            or when bounding boxes cannot be computed.
    """
    if (target_locator is None and offset is None) or (target_locator is not None and offset is not None):
        raise BrowserToolError("Provide exactly one of target_locator or offset", tool="drag")

    cfg = _get_human_config()

    source_handle = await source_locator.element_handle()
    if source_handle is None:
        raise BrowserToolError("Unable to resolve source element handle", tool="drag")

    source_frame = await source_handle.owner_frame()
    if source_frame is None:
        raise BrowserToolError(
            "Source element is not attached to a frame/page; cannot perform drag",
            tool="drag",
        )

    source_box = await source_handle.bounding_box()
    if source_box is None or source_box.get("width", 0) < 4 or source_box.get("height", 0) < 4:
        label_handle = None
        try:
            label_handle = await source_handle.evaluate_handle("(el) => el.labels?.[0] ?? null")
        except PlaywrightError as exc:
            logger.warning(
                "Failed to evaluate source label handle; using element's own bounding box if available. Error: %s",
                exc,
            )
            label_handle = None
        if label_handle is not None:
            try:
                label_element = label_handle.as_element()
                if label_element is not None:
                    label_box = await label_element.bounding_box()
                    if label_box and label_box.get("width", 0) >= 4 and label_box.get("height", 0) >= 4:
                        source_box = label_box
            finally:
                try:
                    await label_handle.dispose()
                except PlaywrightError as exc:
                    logger.warning("Failed to dispose source label handle; continuing. Error: %s", exc)

    if source_box is None or source_box.get("width", 0) <= 0 or source_box.get("height", 0) <= 0:
        raise BrowserToolError("Source element has no bounding box to drag", tool="drag")

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="drag")

    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2

    if cfg.offset_px > 0:
        angle = random.random() * 2 * math.pi
        radius = random.random() * cfg.offset_px
        start_x += math.cos(angle) * radius
        start_y += math.sin(angle) * radius

    dest_x: float
    dest_y: float

    if target_locator is not None:
        target_handle = await target_locator.element_handle()
        if target_handle is None:
            raise BrowserToolError("Unable to resolve target element handle", tool="drag")

        target_frame = await target_handle.owner_frame()
        if target_frame is None:
            raise BrowserToolError(
                "Target element is not attached to a frame/page; cannot perform drag",
                tool="drag",
            )

        target_box = await target_handle.bounding_box()
        if target_box is None or target_box.get("width", 0) < 4 or target_box.get("height", 0) < 4:
            label_handle = None
            try:
                label_handle = await target_handle.evaluate_handle("(el) => el.labels?.[0] ?? null")
            except PlaywrightError as exc:
                logger.warning(
                    "Failed to evaluate target label handle; using element's own bounding box if available. Error: %s",
                    exc,
                )
                label_handle = None
            if label_handle is not None:
                try:
                    label_element = label_handle.as_element()
                    if label_element is not None:
                        label_box = await label_element.bounding_box()
                        if label_box and label_box.get("width", 0) >= 4 and label_box.get("height", 0) >= 4:
                            target_box = label_box
                finally:
                    try:
                        await label_handle.dispose()
                    except PlaywrightError as exc:
                        logger.warning("Failed to dispose target label handle; continuing. Error: %s", exc)

        if target_box is None or target_box.get("width", 0) <= 0 or target_box.get("height", 0) <= 0:
            raise BrowserToolError("Target element has no bounding box to drag", tool="drag")

        dest_x = target_box["x"] + target_box["width"] / 2
        dest_y = target_box["y"] + target_box["height"] / 2

        if cfg.offset_px > 0:
            angle = random.random() * 2 * math.pi
            radius = random.random() * cfg.offset_px
            dest_x += math.cos(angle) * radius
            dest_y += math.sin(angle) * radius
    else:
        if offset is None:
            raise BrowserToolError("offset must be provided when target_locator is None", tool="drag")
        try:
            dx, dy = offset
        except (TypeError, ValueError) as exc:
            raise BrowserToolError("offset must be a tuple of two values", tool="drag") from exc
        try:
            dest_x = start_x + float(dx)
            dest_y = start_y + float(dy)
        except (TypeError, ValueError) as exc:
            raise BrowserToolError("offset values must be numbers", tool="drag") from exc
        if not (math.isfinite(dest_x) and math.isfinite(dest_y)):
            raise BrowserToolError("offset produced non-finite drag coordinates", tool="drag")

    mouse = page.mouse

    # Move to drag start, press, glide to destination, then release.
    await _mouse_move_with_fake_cursor(page, x=start_x, y=start_y, steps=cfg.move_steps)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await _mouse_move_with_fake_cursor(page, x=dest_x, y=dest_y, steps=max(cfg.move_steps, 2))
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.up()

    # Best-effort overlay update at drag destination.
    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [dest_x, dest_y])
    except PlaywrightError as exc:
        logger.warning(
            (
                "Failed to update fake cursor overlay at drag destination (%s, %s) on page %s; "
                "continuing without overlay update. Error: %s"
            ),
            dest_x,
            dest_y,
            getattr(page, "url", "<unknown>"),
            exc,
        )


async def human_type(page: Page, locator: Locator, text: str, *, clear_existing: bool = True) -> None:
    """Type text into a focused element with human-like delays using an explicit page.

    Args:
        page: Playwright Page object whose keyboard will be used.
        locator: Locator for the input element.
        text: Text to type.
        clear_existing: Whether to clear existing text before typing.

    Raises:
        BrowserToolError: If locator cannot be resolved or page lacks a keyboard.
    """
    cfg = _get_human_config()
    handle = await locator.element_handle()
    if handle is None:
        raise BrowserToolError("Unable to resolve element handle", tool="fill_field")

    # The element must be attached to a frame/page to use the page's
    # keyboard for human-like typing. Previously we fell back to
    # ``locator.fill()`` for test doubles or detached handles; that
    # behavior is not present in production code. Callers must ensure
    # the element is attached to the document of the provided page.
    frame = await handle.owner_frame()
    if frame is None:
        raise BrowserToolError(
            "Element is not attached to a frame/page; cannot perform keyboard-based fill",
            tool="fill_field",
        )

    if not hasattr(page, "keyboard") or page.keyboard is None:
        raise BrowserToolError("Provided page has no keyboard available", tool="fill_field")

    keyboard = page.keyboard
    await locator.focus()

    if clear_existing:
        try:
            await keyboard.press("Control+A")
            await keyboard.press("Backspace")
        except Exception as exc:
            # If keyboard.press fails, raising is preferable to silently using fill.
            raise BrowserToolError("Failed to clear existing text via keyboard", tool="fill_field") from exc

    for idx, ch in enumerate(text):
        delay = random.randint(cfg.delay_min_ms, cfg.delay_max_ms)
        await keyboard.type(ch, delay=delay)
        if cfg.extra_pause_every_chars > 0 and (idx + 1) % cfg.extra_pause_every_chars == 0:
            await _sleep_ms(random.randint(cfg.extra_pause_min_ms, cfg.extra_pause_max_ms))


async def human_press_keys(page: Page, keys: list[str]) -> None:
    """Press one or more keyboard keys on the provided Playwright Page.

    Behavior and contract:
    - Expects an explicit Playwright ``Page`` instance as the first argument.
    - Uses ``page.keyboard`` to perform key presses; if the page has no
      ``keyboard`` attribute (or it is ``None``) a ``BrowserToolError`` is raised.
    - Accepts a list of key strings. Modifier chords are supported using the
      ``+`` separator (for example: "Control+Shift+P"). Each list element is
      processed in order.
    - For a modifier chord the helper presses modifiers down (in order), then
      issues a ``press`` for the base key, and finally releases modifiers in
      reverse order.
    - The function validates input and raises ``BrowserToolError`` for invalid
      inputs or if Playwright operations raise exceptions.

    Note: callers (the interactions/tools layer) are responsible for acquiring
    the active page and passing it in; tests may monkeypatch ``page.keyboard``
    with a dummy object.
    """
    if not isinstance(keys, list) or len(keys) == 0:
        raise BrowserToolError("keys must be a non-empty list of key names", tool="press_keys")

    # The implementation operates directly on the provided page.keyboard.
    # Validate that the page exposes a keyboard API before proceeding.
    if not hasattr(page, "keyboard") or page.keyboard is None:
        raise BrowserToolError("Provided page has no keyboard available", tool="press_keys")

    keyboard = page.keyboard

    for key in keys:
        if not isinstance(key, str) or not key:
            raise BrowserToolError("Each key must be a non-empty string", tool="press_keys")

        parts = key.split("+")
        modifiers = parts[:-1]
        base = parts[-1]

        try:
            # Press modifiers down
            for mod in modifiers:
                await keyboard.down(mod)
                # small jitter between modifier downs
                await _sleep_ms(random.randint(0, 10))

            # Press and release the base key
            await keyboard.press(base)

            # Release modifiers in reverse order
            for mod in reversed(modifiers):
                await keyboard.up(mod)
                await _sleep_ms(random.randint(0, 10))
        except Exception as exc:  # pragma: no cover - bubbling Playwright errors
            raise BrowserToolError(f"Failed to press key '{key}': {exc}", tool="press_keys") from exc


__all__ = ["human_click", "human_drag", "human_press_keys", "human_scroll", "human_type"]


async def human_scroll(page: Page, direction: str = "down", amount: int | None = None) -> None:
    """Perform a human-like scroll on the provided Playwright Page.

    Args:
        page: Playwright Page instance to operate on.
        direction: One of {"down", "up", "page_down", "page_up", "top", "bottom"}.
        amount: Optional pixel distance for fine-grained scrolling when direction is
            "down" or "up". If omitted, a viewport-sized scroll (page-style) is used.

    Raises:
        BrowserToolError: On invalid input or missing page APIs.
    """
    cfg = _get_human_config()

    if not isinstance(direction, str) or not direction:
        raise BrowserToolError("direction must be a non-empty string", tool="scroll_page")

    dir_norm = direction.lower()
    allowed = {"down", "up", "page_down", "page_up", "top", "bottom"}
    if dir_norm not in allowed:
        raise BrowserToolError(f"Invalid scroll direction '{direction}'", tool="scroll_page")

    # Prefer keyboard PageDown/PageUp for page-style scrolling for simplicity.
    # For pixel/step scrolling use window.scroll via evaluate if available.
    try:
        if dir_norm in {"top", "bottom"}:
            key = "Home" if dir_norm == "top" else "End"
            if hasattr(page, "keyboard") and page.keyboard is not None:
                await page.keyboard.press(key)
            else:
                # fallback to evaluate
                await page.evaluate(f"() => window.scrollTo(0, document.{'documentElement'}.{'scrollHeight'} )")
        elif dir_norm in {"page_down", "page_up"}:
            key = "PageDown" if dir_norm == "page_down" else "PageUp"
            if hasattr(page, "keyboard") and page.keyboard is not None:
                await page.keyboard.press(key)
            else:
                # simulate by scrolling by viewport height
                await page.evaluate(
                    "() => { window.scrollBy(0, window.innerHeight * (arguments[0])); }",
                    1 if dir_norm == "page_down" else -1,
                )
        else:
            # 'down' or 'up' with optional pixel amount
            if amount is None:
                # default to viewport scroll using page.viewport_size when available
                if hasattr(page, "viewport_size") and page.viewport_size:
                    height = page.viewport_size.get("height", 800)
                else:
                    height = 800
                delta = round(height) if dir_norm == "down" else -round(height)
            else:
                if not isinstance(amount, int):
                    raise BrowserToolError("amount must be an integer number of pixels", tool="scroll_page")
                delta = amount if dir_norm == "down" else -amount

            # Add jitter using config offset as fraction
            jitter = round(cfg.offset_px) if cfg.offset_px else 0
            if jitter > 0:
                delta += random.randint(-jitter, jitter)

            # Use evaluate to perform smooth-ish scroll
            await page.evaluate(
                "(dy) => window.scrollBy({ top: dy, left: 0, behavior: 'smooth' })",
                delta,
            )

        # small pause to allow lazy loading
        await _sleep_ms(random.randint(100, 300))
    except Exception as exc:  # pragma: no cover - Playwright runtime errors
        raise BrowserToolError(f"Failed to perform scroll: {exc}", tool="scroll_page") from exc
