"""Human-like interaction helpers for browser tools."""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page

from config import load_config
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


@dataclass
class _HumanConfig:
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


def _page_for(target: Page | Frame) -> Page:
    """Extract the ``Page`` from a ``Page | Frame`` for mouse/keyboard input.

    Playwright routes mouse and keyboard events through the compositor, so the
    ``Page`` object is always needed for ``.mouse`` / ``.keyboard`` access.
    When *target* is already a ``Page``, return it directly; when it's a
    ``Frame`` (e.g. a dominant iframe), reach up to its parent ``Page``.

    Uses ``isinstance`` for real Playwright types and falls back to duck-typing
    so that test stubs without Playwright inheritance still work correctly.
    """
    if isinstance(target, Page):
        return target
    if isinstance(target, Frame):
        return target.page
    # Duck-type fallback: if the object has no `.page` attribute it is
    # likely a Page-like stub used in tests — return it directly.
    if hasattr(target, "page"):
        return target.page  # type: ignore[return-value]
    return target  # type: ignore[return-value]


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
    if not installed:
        logger.debug("Fake cursor overlay not present on page %s", getattr(page, "url", "<unknown>"))


def _bezier_point(
    t: float,
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[float, float]:
    """Evaluate a cubic Bezier curve at parameter t (0..1)."""
    u = 1 - t
    x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
    y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
    return x, y


def _ease_in_out(t: float) -> float:
    """Sinusoidal ease-in-out: slow start, fast middle, slow end."""
    return (1 - math.cos(t * math.pi)) / 2


def _build_trajectory(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> list[tuple[float, float]]:
    """Build a natural-looking mouse trajectory using a cubic Bezier curve.

    The trajectory uses random control points offset from the straight line,
    an ease-in-out velocity profile, and per-step micro-jitter to simulate
    hand tremor.  Step count scales with distance (~50px per step).
    """
    dx = end_x - start_x
    dy = end_y - start_y
    dist = math.hypot(dx, dy)

    # Calculate step count from distance — ~50px per step, minimum 2
    adaptive_steps = max(2, int(dist / 50))

    # Generate two random control points offset perpendicular to the line.
    # Offset magnitude scales with distance but caps to avoid wild curves.
    max_offset = min(dist * 0.3, 80)
    offset1 = random.uniform(-max_offset, max_offset)
    offset2 = random.uniform(-max_offset, max_offset)

    # Perpendicular direction (rotate 90 degrees)
    if dist > 0:
        perp_x = -dy / dist
        perp_y = dx / dist
    else:
        perp_x, perp_y = 0.0, 1.0

    # Control points at ~1/3 and ~2/3 along the line, offset perpendicular
    cp1 = (
        start_x + dx * 0.3 + perp_x * offset1,
        start_y + dy * 0.3 + perp_y * offset1,
    )
    cp2 = (
        start_x + dx * 0.7 + perp_x * offset2,
        start_y + dy * 0.7 + perp_y * offset2,
    )

    p0 = (start_x, start_y)
    p3 = (end_x, end_y)

    points: list[tuple[float, float]] = []
    for i in range(1, adaptive_steps + 1):
        # Ease-in-out: remap linear t to slow-fast-slow progression
        t_linear = i / adaptive_steps
        t_eased = _ease_in_out(t_linear)

        bx, by = _bezier_point(t_eased, p0, cp1, cp2, p3)

        # Add micro-jitter (±1.5px) to simulate hand tremor, except on the
        # final step which must land precisely on the target.
        if i < adaptive_steps:
            jitter = 1.5
            bx += random.uniform(-jitter, jitter)
            by += random.uniform(-jitter, jitter)

        points.append((bx, by))

    return points


async def _mouse_move_with_fake_cursor(page: Page, *, x: float, y: float) -> None:
    """Move the Playwright mouse along a natural Bezier trajectory.

    Uses a cubic Bezier curve with random control points, an ease-in-out
    velocity profile, and per-step micro-jitter to produce human-like
    mouse movement. Also updates the in-page fake cursor overlay.
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
                    (
                        "Invalid fake cursor position values %s on page %s; "
                        "using target coordinates as default. Error: %s"
                    ),
                    pos,
                    getattr(page, "url", "<unknown>"),
                    exc,
                )
                sx = x
                sy = y
            # If the stored position is the sentinel off-screen value, treat as unset.
            if not (math.isfinite(sx) and math.isfinite(sy)) or (sx == -9999 and sy == -9999):
                logger.debug(
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

    # Build a natural Bezier trajectory with jitter and ease-in-out pacing.
    trajectory = _build_trajectory(start_x, start_y, x, y)

    for xi, yi in trajectory:
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

        # Fire non-blocking progressive snapshot (throttled to ~4 fps).
        # The emitter coalesces rapid requests so the movement loop is never
        # blocked waiting for screenshot capture.
        from tools.browser.events import request_progressive_screenshot

        request_progressive_screenshot(page)

        # Small pause to let the browser render the overlay movement. Keep this
        # brief to avoid slowing tests too much while still producing visible motion.
        await asyncio.sleep(0.03)


async def human_click(target: Page | Frame, locator: Locator) -> None:
    """Perform a human-like click on an element using an explicit Playwright page.

    Args:
        target: Playwright Page or Frame whose mouse will be used to perform the click.
        locator: Locator identifying the element to click.

    Raises:
        BrowserToolError: If the locator cannot be resolved or the page lacks a mouse.
    """
    page = _page_for(target)
    cfg = _get_human_config()
    if hasattr(locator, "scroll_into_view_if_needed"):
        try:
            await locator.scroll_into_view_if_needed(timeout=5000)
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("scroll_into_view_if_needed failed prior to click: %s", exc)
    handle = await locator.element_handle(timeout=5000)
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

    # Add small random offset within the element (~10% of dimensions)
    jitter_x = box["width"] * 0.1
    jitter_y = box["height"] * 0.1
    target_x += random.uniform(-jitter_x, jitter_x)
    target_y += random.uniform(-jitter_y, jitter_y)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await mouse.up()
    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [target_x, target_y])
        # Small delay after positioning cursor to allow CSS transition to render
        # This ensures screenshots captured shortly after will show the cursor
        await asyncio.sleep(0.05)
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


async def human_press_and_hold(
    target: Page | Frame,
    locator: Locator,
    duration_ms: int = 3000,
) -> None:
    """Press and hold an element for a specified duration.

    Performs the same human-like positioning as ``human_click`` but holds the
    mouse button down for ``duration_ms`` milliseconds before releasing. Fires
    progressive snapshots during the hold so the caller can observe progress.

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        locator: Locator identifying the element to press and hold.
        duration_ms: How long to hold the mouse button down in milliseconds.

    Raises:
        BrowserToolError: If the locator cannot be resolved or the page lacks a mouse.
    """
    page = _page_for(target)
    cfg = _get_human_config()
    if hasattr(locator, "scroll_into_view_if_needed"):
        try:
            await locator.scroll_into_view_if_needed(timeout=5000)
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.debug("scroll_into_view_if_needed failed prior to press_and_hold: %s", exc)
    handle = await locator.element_handle(timeout=5000)
    if handle is None:
        raise BrowserToolError("Unable to resolve element handle", tool="press_and_hold")

    frame = await handle.owner_frame()
    if frame is None:
        raise BrowserToolError(
            "Element is not attached to a frame/page; cannot perform press_and_hold",
            tool="press_and_hold",
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
        raise BrowserToolError("Element has no bounding box to press", tool="press_and_hold")

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="press_and_hold")

    target_x = box["x"] + box["width"] / 2
    target_y = box["y"] + box["height"] / 2

    jitter_x = box["width"] * 0.1
    jitter_y = box["height"] * 0.1
    target_x += random.uniform(-jitter_x, jitter_x)
    target_y += random.uniform(-jitter_y, jitter_y)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()

    # Hold for the requested duration, firing progressive snapshots so the
    # agent (and streaming UI) can observe progress (e.g. a filling progress bar).
    from tools.browser.events import request_progressive_screenshot

    hold_duration = max(0, duration_ms)
    snapshot_interval_ms = 250
    elapsed = 0
    while elapsed < hold_duration:
        chunk = min(snapshot_interval_ms, hold_duration - elapsed)
        await _sleep_ms(chunk)
        elapsed += chunk
        request_progressive_screenshot(page)

    await mouse.up()

    # Best-effort overlay update at the hold point.
    try:
        await page.evaluate(
            "(coords) => window.__llmCursorSet?.(coords[0], coords[1])",
            [target_x, target_y],
        )
        await asyncio.sleep(0.05)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to finalize fake cursor overlay at press_and_hold point (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            target_x,
            target_y,
            getattr(page, "url", "<unknown>"),
            exc,
        )


async def human_drag(
    target: Page | Frame,
    source_locator: Locator,
    *,
    target_locator: Locator,
) -> None:
    """Drag from ``source_locator`` to ``target_locator``.

    Args:
        target: Playwright Page or Frame whose mouse will be used for the drag.
        source_locator: Locator identifying the element where the drag should begin.
        target_locator: Locator identifying the destination element.

    Raises:
        BrowserToolError: On invalid inputs, detached elements, missing mouse APIs,
            or when bounding boxes cannot be computed.
    """
    page = _page_for(target)

    cfg = _get_human_config()

    source_handle = await source_locator.element_handle(timeout=5000)
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

    jitter_x = source_box["width"] * 0.1
    jitter_y = source_box["height"] * 0.1
    start_x += random.uniform(-jitter_x, jitter_x)
    start_y += random.uniform(-jitter_y, jitter_y)

    target_handle = await target_locator.element_handle(timeout=5000)
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

    jitter_x = target_box["width"] * 0.1
    jitter_y = target_box["height"] * 0.1
    dest_x += random.uniform(-jitter_x, jitter_x)
    dest_y += random.uniform(-jitter_y, jitter_y)

    mouse = page.mouse

    # Move to drag start, press, glide to destination, then release.
    await _mouse_move_with_fake_cursor(page, x=start_x, y=start_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await _mouse_move_with_fake_cursor(page, x=dest_x, y=dest_y)
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


async def human_type(target: Page | Frame, locator: Locator, text: str, *, clear_existing: bool = True) -> None:
    """Type text into a focused element with human-like delays using an explicit page.

    Args:
        target: Playwright Page or Frame whose keyboard will be used.
        locator: Locator for the input element (should already be focused/clicked).
        text: Text to type.
        clear_existing: Whether to clear existing text before typing.

    Raises:
        BrowserToolError: If locator cannot be resolved or page lacks a keyboard.
    """
    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "keyboard") or page.keyboard is None:
        raise BrowserToolError("Provided page has no keyboard available", tool="fill_field")

    keyboard = page.keyboard

    if clear_existing:
        try:
            await keyboard.press("Control+A")
            await keyboard.press("Backspace")
        except Exception as exc:
            # If keyboard.press fails, raising is preferable to silently using fill.
            raise BrowserToolError("Failed to clear existing text via keyboard", tool="fill_field") from exc

    for idx, ch in enumerate(text):
        delay = random.randint(cfg.delay_min_ms, cfg.delay_max_ms)
        # Type single character (keyboard.type handles single chars fine)
        await keyboard.type(ch)
        # Add human-like delay after typing
        if delay > 0:
            await _sleep_ms(delay)

        # Fire non-blocking progressive snapshot (throttled to ~4 fps).
        from tools.browser.events import request_progressive_screenshot

        request_progressive_screenshot(page)

        if cfg.extra_pause_every_chars > 0 and (idx + 1) % cfg.extra_pause_every_chars == 0:
            await _sleep_ms(random.randint(cfg.extra_pause_min_ms, cfg.extra_pause_max_ms))


async def human_press_keys(target: Page | Frame, keys: list[str]) -> None:
    """Press one or more keyboard keys on the provided Playwright Page.

    Behavior and contract:
    - Expects an explicit Playwright ``Page`` or ``Frame`` instance as the
      first argument. The underlying ``Page`` is extracted for keyboard access.
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
    page = _page_for(target)
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


def _random_point_in_bbox(
    x1: float, y1: float, x2: float, y2: float,
) -> tuple[float, float]:
    """Pick a random point inside a bounding box, biased toward the center.

    Uses a truncated gaussian (clamped to bbox) so clicks cluster naturally
    near the center but still vary across the full element area.
    """
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    # Sigma = 1/4 of dimension so ~95% of samples fall within the bbox
    sx = max((x2 - x1) / 4.0, 0.5)
    sy = max((y2 - y1) / 4.0, 0.5)
    px = max(x1, min(x2, random.gauss(cx, sx)))
    py = max(y1, min(y2, random.gauss(cy, sy)))
    return px, py


async def human_click_at(
    target: Page | Frame,
    x1: float, y1: float, x2: float, y2: float,
) -> None:
    """Perform a human-like click at a random point inside a bounding box.

    Bypasses locator/bounding-box resolution entirely, allowing clicks on
    elements that cannot be resolved to a DOM selector (shadow DOM, iframes,
    dynamically injected content).

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).

    Raises:
        BrowserToolError: If coordinates are non-finite or the page lacks a mouse.
    """
    coords = (x1, y1, x2, y2)
    if not all(math.isfinite(c) for c in coords):
        raise BrowserToolError("Coordinates must be finite numbers", tool="click_at")

    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="click_at")

    target_x, target_y = _random_point_in_bbox(x1, y1, x2, y2)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await mouse.up()

    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [target_x, target_y])
        await asyncio.sleep(0.05)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to finalize fake cursor overlay at click_at point (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            target_x,
            target_y,
            getattr(page, "url", "<unknown>"),
            exc,
        )


async def human_press_and_hold_at(
    target: Page | Frame,
    x1: float, y1: float, x2: float, y2: float,
    duration_ms: int = 3000,
) -> None:
    """Press and hold at a random point inside a bounding box for a duration.

    Bypasses locator/bounding-box resolution entirely. Fires progressive
    snapshots during the hold so the caller can observe progress.

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).
        duration_ms: How long to hold the mouse button down in milliseconds.

    Raises:
        BrowserToolError: If coordinates are non-finite or the page lacks a mouse.
    """
    coords = (x1, y1, x2, y2)
    if not all(math.isfinite(c) for c in coords):
        raise BrowserToolError("Coordinates must be finite numbers", tool="press_and_hold_at")

    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="press_and_hold_at")

    target_x, target_y = _random_point_in_bbox(x1, y1, x2, y2)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()

    # Hold for the requested duration, firing progressive snapshots.
    from tools.browser.events import request_progressive_screenshot

    hold_duration = max(0, duration_ms)
    snapshot_interval_ms = 250
    elapsed = 0
    while elapsed < hold_duration:
        chunk = min(snapshot_interval_ms, hold_duration - elapsed)
        await _sleep_ms(chunk)
        elapsed += chunk
        request_progressive_screenshot(page)

    await mouse.up()

    # Best-effort overlay update at the hold point.
    try:
        await page.evaluate(
            "(coords) => window.__llmCursorSet?.(coords[0], coords[1])",
            [target_x, target_y],
        )
        await asyncio.sleep(0.05)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to finalize fake cursor overlay at press_and_hold_at point (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            target_x,
            target_y,
            getattr(page, "url", "<unknown>"),
            exc,
        )


async def human_double_click_at(
    target: Page | Frame,
    x1: float, y1: float, x2: float, y2: float,
) -> None:
    """Perform a human-like double-click at a random point inside a bounding box.

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).

    Raises:
        BrowserToolError: If coordinates are non-finite or the page lacks a mouse.
    """
    coords = (x1, y1, x2, y2)
    if not all(math.isfinite(c) for c in coords):
        raise BrowserToolError("Coordinates must be finite numbers", tool="double_click_at")

    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="double_click_at")

    target_x, target_y = _random_point_in_bbox(x1, y1, x2, y2)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))

    # Use Playwright's native dblclick to guarantee the browser fires a
    # 'dblclick' DOM event. Manual down/up pairs can miss the timing
    # window depending on browser configuration.
    await mouse.dblclick(target_x, target_y)

    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [target_x, target_y])
        await asyncio.sleep(0.05)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to finalize fake cursor overlay at double_click_at point (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            target_x, target_y, getattr(page, "url", "<unknown>"), exc,
        )


async def human_right_click_at(
    target: Page | Frame,
    x1: float, y1: float, x2: float, y2: float,
) -> None:
    """Perform a human-like right-click at a random point inside a bounding box.

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).

    Raises:
        BrowserToolError: If coordinates are non-finite or the page lacks a mouse.
    """
    coords = (x1, y1, x2, y2)
    if not all(math.isfinite(c) for c in coords):
        raise BrowserToolError("Coordinates must be finite numbers", tool="right_click_at")

    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="right_click_at")

    target_x, target_y = _random_point_in_bbox(x1, y1, x2, y2)

    mouse = page.mouse
    await _mouse_move_with_fake_cursor(page, x=target_x, y=target_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down(button="right")
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await mouse.up(button="right")

    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [target_x, target_y])
        await asyncio.sleep(0.05)
    except PlaywrightError as exc:
        logger.warning(
            "Failed to finalize fake cursor overlay at right_click_at point (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            target_x, target_y, getattr(page, "url", "<unknown>"), exc,
        )


async def human_drag_at(
    target: Page | Frame,
    sx1: float, sy1: float, sx2: float, sy2: float,
    dx1: float, dy1: float, dx2: float, dy2: float,
) -> None:
    """Drag from a random point in the source bbox to a random point in the dest bbox.

    Args:
        target: Playwright Page or Frame whose mouse will be used.
        sx1, sy1, sx2, sy2: Source bounding box (CSS pixels).
        dx1, dy1, dx2, dy2: Destination bounding box (CSS pixels).

    Raises:
        BrowserToolError: If coordinates are non-finite or the page lacks a mouse.
    """
    all_coords = (sx1, sy1, sx2, sy2, dx1, dy1, dx2, dy2)
    if not all(math.isfinite(c) for c in all_coords):
        raise BrowserToolError("Coordinates must be finite numbers", tool="drag_at")

    page = _page_for(target)
    cfg = _get_human_config()

    if not hasattr(page, "mouse") or page.mouse is None:
        raise BrowserToolError("Provided page has no mouse available", tool="drag_at")

    start_x, start_y = _random_point_in_bbox(sx1, sy1, sx2, sy2)
    dest_x, dest_y = _random_point_in_bbox(dx1, dy1, dx2, dy2)

    mouse = page.mouse

    # Move to drag start, press, glide to destination, then release.
    await _mouse_move_with_fake_cursor(page, x=start_x, y=start_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await _mouse_move_with_fake_cursor(page, x=dest_x, y=dest_y)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.up()

    try:
        await page.evaluate("(coords) => window.__llmCursorSet?.(coords[0], coords[1])", [dest_x, dest_y])
    except PlaywrightError as exc:
        logger.warning(
            "Failed to update fake cursor overlay at drag_at destination (%s, %s) on page %s; "
            "continuing without overlay update. Error: %s",
            dest_x, dest_y, getattr(page, "url", "<unknown>"), exc,
        )


__all__ = [
    "human_click",
    "human_click_at",
    "human_double_click_at",
    "human_drag",
    "human_drag_at",
    "human_press_and_hold",
    "human_press_and_hold_at",
    "human_press_keys",
    "human_right_click_at",
    "human_scroll",
    "human_type",
]


async def human_scroll(target: Page | Frame, direction: str = "down", amount: int | None = None) -> None:
    """Perform a human-like scroll on the provided Playwright Page or Frame.

    Args:
        target: Playwright Page or Frame instance to operate on. When a Frame is
            provided, scroll-related JS evaluations run inside the frame's window
            context so iframes scroll correctly.
        direction: One of {"down", "up", "page_down", "page_up", "top", "bottom"}.
        amount: Optional pixel distance for fine-grained scrolling when direction is
            "down" or "up". If omitted, a viewport-sized scroll (page-style) is used.

    Raises:
        BrowserToolError: On invalid input or missing page APIs.
    """
    page = _page_for(target)
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
                # fallback to evaluate — run in target context so iframes scroll
                await target.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        elif dir_norm in {"page_down", "page_up"}:
            key = "PageDown" if dir_norm == "page_down" else "PageUp"
            if hasattr(page, "keyboard") and page.keyboard is not None:
                await page.keyboard.press(key)
            else:
                # simulate by scrolling by viewport height — run in target context
                await target.evaluate(
                    "() => { window.scrollBy(0, window.innerHeight * (arguments[0])); }",
                    1 if dir_norm == "page_down" else -1,
                )
        else:
            # 'down' or 'up' with optional pixel amount
            if amount is None:
                # Query actual viewport height from the browser
                try:
                    height = await target.evaluate("() => window.innerHeight")
                    if not isinstance(height, int | float) or height <= 0:
                        height = 800  # fallback
                except PlaywrightError:
                    height = 800  # fallback if evaluate fails
                delta = round(height) if dir_norm == "down" else -round(height)
            else:
                if not isinstance(amount, int):
                    raise BrowserToolError("amount must be an integer number of pixels", tool="scroll_page")
                delta = amount if dir_norm == "down" else -amount

            # Add small jitter to scroll distance
            delta += random.randint(-4, 4)

            # Perform smooth scrolling with multiple wheel events to mimic human scrolling
            # Humans don't jump-scroll; they use mouse wheel in small increments
            if not hasattr(page, "mouse") or page.mouse is None:
                # Fallback to evaluate if mouse API unavailable — run in target context
                await target.evaluate(
                    "(dy) => window.scrollBy({ top: dy, left: 0, behavior: 'smooth' })",
                    delta,
                )
            else:
                # Split scroll into multiple small wheel events
                wheel_increment = 50 if delta > 0 else -50
                remaining = abs(delta)
                events_count = max(1, remaining // abs(wheel_increment))

                for _i in range(int(events_count)):
                    await page.mouse.wheel(0, wheel_increment)

                    # Fire non-blocking progressive snapshot (throttled to ~4 fps).
                    from tools.browser.events import request_progressive_screenshot

                    request_progressive_screenshot(page)

                    # Small delay between wheel events (16ms = ~60fps scrolling)
                    await asyncio.sleep(0.016)

                # Handle any remainder
                remainder = remaining % abs(wheel_increment)
                if remainder > 0:
                    final_delta = remainder if delta > 0 else -remainder
                    await page.mouse.wheel(0, final_delta)
                    await asyncio.sleep(0.016)

        # small pause to allow lazy loading
        await _sleep_ms(random.randint(100, 300))
    except Exception as exc:  # pragma: no cover - Playwright runtime errors
        raise BrowserToolError(f"Failed to perform scroll: {exc}", tool="scroll_page") from exc
