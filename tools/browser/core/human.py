"""Human-like interaction helpers for browser tools."""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass

from playwright.async_api import Locator, Page

from config import load_config
from tools.browser.core.exceptions import BrowserToolError


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


async def human_click(page: Page, locator: Locator) -> None:
    """Perform a human-like click on a locator using an explicit Playwright page.

    Args:
        page: Playwright Page object whose mouse will be used to perform the click.
        locator: Playwright Locator identifying the element to click.

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
    if box is None:
        # No bounding box; the caller should ensure a visible element selector.
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
    await mouse.move(target_x, target_y, steps=cfg.move_steps)
    await _sleep_ms(random.randint(cfg.hover_min_ms, cfg.hover_max_ms))
    await mouse.down()
    await _sleep_ms(random.randint(cfg.click_hold_min_ms, cfg.click_hold_max_ms))
    await mouse.up()


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


__all__ = ["human_click", "human_press_keys", "human_type"]
