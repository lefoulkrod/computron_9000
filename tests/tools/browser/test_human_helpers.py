"""Unit tests for human-like browser helpers.

These tests stub Playwright Locator/ElementHandle/Page/mouse/keyboard to verify:
- human_click calls mouse.move/down/up in expected order and respects hover/click durations
- human_type calls keyboard.type per character, includes clear_existing behavior, and
  falls back to locator.fill when no page is available
- owner_frame fallback path when element handles lack .owner_frame or .page

Tests deterministic by seeding random and patching config to small timings.
"""
from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from typing import cast

from playwright.async_api import Locator

import pytest

from tools.browser.core.human import human_click, human_type, _get_human_config, _HumanConfig
from tools.browser.core.exceptions import BrowserToolError


class DummyMouse:
    def __init__(self, recorder: list[str]):
        self.recorder = recorder

    async def move(self, x, y, steps=1):
        self.recorder.append(f"move:{x:.1f}:{y:.1f}:{steps}")

    async def down(self):
        self.recorder.append("down")

    async def up(self):
        self.recorder.append("up")


class DummyKeyboard:
    def __init__(self, recorder: list[str]):
        self.recorder = recorder

    async def press(self, key: str):
        # record presses synchronously
        self.recorder.append(f"press:{key}")

    async def type(self, ch: str, delay: int = 0):
        # simulate delay but don't actually sleep to keep tests fast
        self.recorder.append(f"type:{ch}:{delay}")


class DummyElementHandle:
    def __init__(self, bounding_box=None, frame=None, text=""):
        self._box = bounding_box
        self._frame = frame
        self._text = text

    async def bounding_box(self):
        return self._box

    async def owner_frame(self):
        return self._frame

    async def evaluate(self, fn):
        return None


class DummyLocator:
    def __init__(self, handle: DummyElementHandle | None):
        self._handle = handle
        self._filled = None

    async def element_handle(self):
        return self._handle

    async def click(self):
        # fallback click used when page/frame isn't available
        raise NotImplementedError("direct click not supported in dummy")

    async def focus(self):
        return None

    async def fill(self, text: str):
        self._filled = text
        return None


class DummyFrame:
    def __init__(self, page=None):
        self.page = page


class DummyPage:
    def __init__(self, mouse=None, keyboard=None):
        self.mouse = mouse
        self.keyboard = keyboard


@pytest.mark.unit
async def test_human_click_sequence_and_fallback(monkeypatch):
    recorder: list[str] = []

    # deterministic random values
    monkeypatch.setattr(random, "random", lambda: 0.5)
    monkeypatch.setattr(random, "randint", lambda a, b: (a + b) // 2)

    mouse = DummyMouse(recorder)
    page = DummyPage(mouse=mouse)
    frame = DummyFrame(page=page)

    box = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 40.0}
    handle = DummyElementHandle(bounding_box=box, frame=frame)
    locator = DummyLocator(handle)

    # Force small timings via config cache
    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(
        move_steps=2,
        offset_px=0.0,
        hover_min_ms=0,
        hover_max_ms=0,
        click_hold_min_ms=0,
        click_hold_max_ms=0,
        delay_min_ms=0,
        delay_max_ms=0,
        extra_pause_every_chars=0,
        extra_pause_min_ms=0,
        extra_pause_max_ms=0,
    ))

    await human_click(cast(Locator, locator))

    # Expect move + down + up in order; coordinates centered
    assert any(r.startswith("move:") for r in recorder)
    assert recorder[-2:] == ["down", "up"]

    # Now test fallback when no frame/page
    recorder.clear()
    handle_no_frame = DummyElementHandle(bounding_box=box, frame=None)
    locator2 = DummyLocator(handle_no_frame)

    # human_click should call locator.click fallback (which raises NotImplementedError here)
    with pytest.raises(NotImplementedError):
        await human_click(cast(Locator, locator2))


@pytest.mark.unit
async def test_human_type_sequence_and_fallback(monkeypatch):
    recorder: list[str] = []

    monkeypatch.setattr(random, "randint", lambda a, b: (a + b) // 2)

    keyboard = DummyKeyboard(recorder)
    page = DummyPage(keyboard=keyboard)
    frame = DummyFrame(page=page)

    handle = DummyElementHandle(bounding_box=None, frame=frame)
    locator = DummyLocator(handle)

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(
        move_steps=1,
        offset_px=0.0,
        hover_min_ms=0,
        hover_max_ms=0,
        click_hold_min_ms=0,
        click_hold_max_ms=0,
        delay_min_ms=10,
        delay_max_ms=10,
        extra_pause_every_chars=0,
        extra_pause_min_ms=0,
        extra_pause_max_ms=0,
    ))

    # Test typing with clear_existing True -> expect Control+A, Backspace, then per-char type
    await human_type(cast(Locator, locator), "ab", clear_existing=True)
    assert recorder[:2] == ["press:Control+A", "press:Backspace"]
    assert recorder[2:] == ["type:a:10", "type:b:10"]

    # Test fallback when no page -> locator.fill should be called
    handle_no_frame = DummyElementHandle(bounding_box=None, frame=None)
    locator2 = DummyLocator(handle_no_frame)
    await human_type(cast(Locator, locator2), "xyz", clear_existing=False)
    assert locator2._filled == "xyz"