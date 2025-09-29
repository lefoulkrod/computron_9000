"""Human-like interaction helpers for browser tools."""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass

from playwright.async_api import Locator

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


async def human_click(locator: Locator) -> None:
    """Perform a human-like click on a locator."""
    cfg = _get_human_config()
    handle = await locator.element_handle()
    if handle is None:
        raise BrowserToolError("Unable to resolve element handle", tool="click")

    box = await handle.bounding_box()
    if box is None:
        await locator.click()
        return

    frame = await handle.owner_frame()
    page = frame.page if frame is not None else None
    if page is None:
        await locator.click()
        return

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


async def human_type(locator: Locator, text: str, *, clear_existing: bool = True) -> None:
    """Type text into a focused element with human-like delays."""
    cfg = _get_human_config()
    handle = await locator.element_handle()
    if handle is None:
        raise BrowserToolError("Unable to resolve element handle", tool="fill_field")

    frame = await handle.owner_frame()
    page = frame.page if frame is not None else None
    if page is None:
        await locator.fill(text)
        return

    keyboard = page.keyboard
    await locator.focus()

    if clear_existing:
        try:
            await keyboard.press("Control+A")
            await keyboard.press("Backspace")
        except Exception:  # noqa: BLE001 - safe fallback
            await locator.fill("")

    for idx, ch in enumerate(text):
        delay = random.randint(cfg.delay_min_ms, cfg.delay_max_ms)
        await keyboard.type(ch, delay=delay)
        if cfg.extra_pause_every_chars > 0 and (idx + 1) % cfg.extra_pause_every_chars == 0:
            await _sleep_ms(random.randint(cfg.extra_pause_min_ms, cfg.extra_pause_max_ms))


__all__ = ["human_click", "human_type"]
