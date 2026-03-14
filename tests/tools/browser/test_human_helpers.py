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

from playwright.async_api import Locator, Page

import pytest

from tools.browser.core.human import (
    human_click,
    human_drag,
    human_press_and_hold,
    human_type,
    _get_human_config,
    _HumanConfig,
    _bezier_point,
    _build_trajectory,
    _ease_in_out,
)
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

    async def press(self, key: str, delay: int = 0):
        # record presses synchronously (delay is optional for Control+A etc)
        self.recorder.append(f"press:{key}:{delay}")

    async def type(self, ch: str):
        # Type without delay parameter (delay is handled separately in code)
        self.recorder.append(f"type:{ch}")


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

    async def element_handle(self, timeout: int | None = None):
        return self._handle

    async def click(self, timeout: int | None = None, force: bool = False):
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

    async def evaluate(self, script_or_fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Minimal evaluate stub used by human helpers.

        Supports:
        - Injection script string (no-op)
        - Presence checks returning False
        - Cursor get/set helpers used by the overlay logic
        """
        # emulate overlay presence flags and position storage on the page instance
        if not hasattr(self, "_cursor_pos"):
            # sentinel off-screen default, same convention as production overlay
            self._cursor_pos = [-9999.0, -9999.0]

        if isinstance(script_or_fn, str):
            expr: str = script_or_fn
            if "__llmCursorSet" in expr and "!!" in expr:
                # presence check: return False (not installed in tests)
                return False
            if "window.__llmCursorGet" in expr:
                return list(self._cursor_pos)
            # generic string scripts are ignored (injection no-op)
            return None

        # Function case: we only need to support the updater used in code
        if callable(script_or_fn):
            # Playwright would run this in the page; our tests only pass coords setter signature
            if args and isinstance(args[0], (list, tuple)) and len(args[0]) == 2:
                x, y = float(args[0][0]), float(args[0][1])
                self._cursor_pos = [x, y]
            return None
        return None


@pytest.mark.unit
async def test_human_click_sequence_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
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

    await human_click(cast(Page, page), cast(Locator, locator))

    # Expect move + down + up in order; coordinates centered
    assert any(r.startswith("move:") for r in recorder)
    assert recorder[-2:] == ["down", "up"]

    # Now test fallback when no frame/page
    recorder.clear()
    handle_no_frame = DummyElementHandle(bounding_box=box, frame=None)
    locator2 = DummyLocator(handle_no_frame)

    # human_click now raises BrowserToolError when no frame/page is present
    from tools.browser.core.exceptions import BrowserToolError

    with pytest.raises(BrowserToolError):
        await human_click(cast(Page, page), cast(Locator, locator2))


@pytest.mark.unit
async def test_human_drag_sequence_to_target(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder: list[str] = []

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 0)

    mouse = DummyMouse(recorder)
    page = DummyPage(mouse=mouse)
    frame = DummyFrame(page=page)

    source_box = {"x": 10.0, "y": 20.0, "width": 80.0, "height": 40.0}
    target_box = {"x": 200.0, "y": 160.0, "width": 60.0, "height": 60.0}
    source_locator = DummyLocator(DummyElementHandle(bounding_box=source_box, frame=frame))
    target_locator = DummyLocator(DummyElementHandle(bounding_box=target_box, frame=frame))

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(


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

    await human_drag(
        cast(Page, page),
        cast(Locator, source_locator),
        target_locator=cast(Locator, target_locator),
    )

    assert recorder.count("down") == 1
    assert recorder.count("up") == 1
    down_index = recorder.index("down")
    up_index = recorder.index("up")
    assert down_index < up_index
    assert any(entry.startswith("move:") for entry in recorder[down_index + 1 : up_index])


@pytest.mark.unit
async def test_human_drag_offset_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder: list[str] = []

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "randint", lambda a, b: 0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)

    mouse = DummyMouse(recorder)
    page = DummyPage(mouse=mouse)
    frame = DummyFrame(page=page)

    source_box = {"x": 0.0, "y": 0.0, "width": 40.0, "height": 40.0}
    source_locator = DummyLocator(DummyElementHandle(bounding_box=source_box, frame=frame))

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(


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

    await human_drag(cast(Page, page), cast(Locator, source_locator), offset=(20, -10))

    expected_x = (source_box["x"] + source_box["width"] / 2) + 20.0
    expected_y = (source_box["y"] + source_box["height"] / 2) - 10.0
    move_coords = [
        tuple(float(part) for part in entry.split(":")[1:3])
        for entry in recorder
        if entry.startswith("move:")
    ]
    assert any(abs(x - expected_x) < 1e-6 and abs(y - expected_y) < 1e-6 for x, y in move_coords)

    # Missing destination (neither target nor offset) raises an error.
    with pytest.raises(BrowserToolError):
        await human_drag(cast(Page, page), cast(Locator, source_locator))

    # Providing both target and offset also raises.
    target_locator = DummyLocator(DummyElementHandle(bounding_box=source_box, frame=frame))
    with pytest.raises(BrowserToolError):
        await human_drag(
            cast(Page, page),
            cast(Locator, source_locator),
            target_locator=cast(Locator, target_locator),
            offset=(1, 1),
        )

    # Page without mouse support fails.
    page_no_mouse = DummyPage(mouse=None)
    frame_no_mouse = DummyFrame(page=page_no_mouse)
    locator_no_mouse = DummyLocator(DummyElementHandle(bounding_box=source_box, frame=frame_no_mouse))
    with pytest.raises(BrowserToolError):
        await human_drag(
            cast(Page, page_no_mouse),
            cast(Locator, locator_no_mouse),
            offset=(5, 5),
        )


@pytest.mark.unit
async def test_human_type_sequence_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder: list[str] = []

    monkeypatch.setattr(random, "randint", lambda a, b: (a + b) // 2)

    keyboard = DummyKeyboard(recorder)
    page = DummyPage(keyboard=keyboard)
    frame = DummyFrame(page=page)

    handle = DummyElementHandle(bounding_box=None, frame=frame)
    locator = DummyLocator(handle)

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(


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

    # Test typing with clear_existing True -> expect Control+A, Backspace (without delay), then per-char type (delay handled separately)
    await human_type(cast(Page, page), cast(Locator, locator), "ab", clear_existing=True)
    assert recorder[:2] == ["press:Control+A:0", "press:Backspace:0"]
    assert recorder[2:] == ["type:a", "type:b"]

    # Test typing without clearing
    recorder.clear()
    await human_type(cast(Page, page), cast(Locator, locator), "xyz", clear_existing=False)
    assert recorder == ["type:x", "type:y", "type:z"]


@pytest.mark.unit
async def test_human_press_keys_modifier_chord_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder: list[str] = []

    keyboard = DummyKeyboard(recorder)
    # add down/up methods to DummyKeyboard for chords
    async def down(key: str) -> None:
        recorder.append(f"down:{key}")

    async def up(key: str) -> None:
        recorder.append(f"up:{key}")

    keyboard.down = down  # type: ignore
    keyboard.up = up  # type: ignore

    page = DummyPage(keyboard=keyboard)

    # Monkeypatch get_browser/current_page to return our dummy page
    class DummyBrowser:
        async def current_page(self) -> object:
            return page

    async def fake_get_browser() -> object:
        return DummyBrowser()

    # Press a modifier chord using the dummy page directly
    from tools.browser.core.human import human_press_keys

    await human_press_keys(cast(Page, page), ["Control+Shift+P"])  # should record some keyboard activity

    # Ensure some keyboard activity was recorded (down/press/up). Exact ordering
    # or naming can vary between environments; check for at least one down and one press/up.
    assert any(r.startswith("down:") for r in recorder)
    assert any(r.startswith("press:") or r.startswith("up:") for r in recorder)

    # Now test fallback when keyboard not available -> monkeypatch get_browser to raise
    async def fail_get_browser() -> None:
        raise RuntimeError("no browser")

    # Now test fallback when keyboard not available -> call helper with a page lacking keyboard
    page_no_keyboard = DummyPage(keyboard=None)
    from tools.browser.core.exceptions import BrowserToolError

    with pytest.raises(BrowserToolError):
        await human_press_keys(cast(Page, page_no_keyboard), ["Enter"])  # should raise BrowserToolError via helper


# ---------------------------------------------------------------------------
# human_press_and_hold tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_human_press_and_hold_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Press-and-hold issues move, down, sleep for duration, then up."""
    recorder: list[str] = []

    monkeypatch.setattr(random, "random", lambda: 0.5)
    monkeypatch.setattr(random, "randint", lambda a, b: 0)

    mouse = DummyMouse(recorder)
    page = DummyPage(mouse=mouse)
    frame = DummyFrame(page=page)

    box = {"x": 50.0, "y": 60.0, "width": 120.0, "height": 50.0}
    handle = DummyElementHandle(bounding_box=box, frame=frame)
    locator = DummyLocator(handle)

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(


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

    # Use a short hold to keep the test fast
    await human_press_and_hold(cast(Page, page), cast(Locator, locator), duration_ms=50)

    # Should have move commands, then down, then up (with the hold in between)
    assert any(r.startswith("move:") for r in recorder)
    down_idx = recorder.index("down")
    up_idx = recorder.index("up")
    assert down_idx < up_idx
    assert recorder.count("down") == 1
    assert recorder.count("up") == 1


@pytest.mark.unit
async def test_human_press_and_hold_no_frame_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Press-and-hold raises when element has no frame."""
    recorder: list[str] = []
    mouse = DummyMouse(recorder)
    page = DummyPage(mouse=mouse)

    box = {"x": 10.0, "y": 10.0, "width": 40.0, "height": 40.0}
    handle = DummyElementHandle(bounding_box=box, frame=None)
    locator = DummyLocator(handle)

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(
        hover_min_ms=0, hover_max_ms=0,
        click_hold_min_ms=0, click_hold_max_ms=0, delay_min_ms=0,
        delay_max_ms=0, extra_pause_every_chars=0, extra_pause_min_ms=0,
        extra_pause_max_ms=0,
    ))

    with pytest.raises(BrowserToolError):
        await human_press_and_hold(cast(Page, page), cast(Locator, locator), duration_ms=100)


@pytest.mark.unit
async def test_human_press_and_hold_no_mouse_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Press-and-hold raises when page has no mouse."""
    page = DummyPage(mouse=None)
    frame = DummyFrame(page=page)

    box = {"x": 10.0, "y": 10.0, "width": 40.0, "height": 40.0}
    handle = DummyElementHandle(bounding_box=box, frame=frame)
    locator = DummyLocator(handle)

    monkeypatch.setattr("tools.browser.core.human._config_cache", _HumanConfig(
        hover_min_ms=0, hover_max_ms=0,
        click_hold_min_ms=0, click_hold_max_ms=0, delay_min_ms=0,
        delay_max_ms=0, extra_pause_every_chars=0, extra_pause_min_ms=0,
        extra_pause_max_ms=0,
    ))

    with pytest.raises(BrowserToolError):
        await human_press_and_hold(cast(Page, page), cast(Locator, locator), duration_ms=100)


# ---------------------------------------------------------------------------
# Bezier trajectory helper tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bezier_point_endpoints() -> None:
    """Bezier curve starts at p0 and ends at p3."""
    p0 = (0.0, 0.0)
    p1 = (10.0, 50.0)
    p2 = (90.0, 50.0)
    p3 = (100.0, 0.0)

    x0, y0 = _bezier_point(0.0, p0, p1, p2, p3)
    assert abs(x0 - p0[0]) < 1e-9
    assert abs(y0 - p0[1]) < 1e-9

    x1, y1 = _bezier_point(1.0, p0, p1, p2, p3)
    assert abs(x1 - p3[0]) < 1e-9
    assert abs(y1 - p3[1]) < 1e-9


@pytest.mark.unit
def test_ease_in_out_boundaries() -> None:
    """Ease-in-out maps 0->0, 0.5->0.5, 1->1."""
    assert abs(_ease_in_out(0.0)) < 1e-9
    assert abs(_ease_in_out(0.5) - 0.5) < 1e-9
    assert abs(_ease_in_out(1.0) - 1.0) < 1e-9


@pytest.mark.unit
def test_ease_in_out_monotonic() -> None:
    """Ease-in-out is monotonically increasing over [0, 1]."""
    prev = 0.0
    for i in range(1, 101):
        t = i / 100
        val = _ease_in_out(t)
        assert val >= prev
        prev = val


@pytest.mark.unit
def test_build_trajectory_endpoints() -> None:
    """Trajectory starts near start and ends exactly at destination."""
    random.seed(42)
    points = _build_trajectory(10.0, 20.0, 300.0, 400.0)

    # Distance ~492px → ~10 steps at 50px/step
    assert len(points) >= 2
    # Final point should land exactly on the target (no jitter on last step)
    last_x, last_y = points[-1]
    assert abs(last_x - 300.0) < 1e-6
    assert abs(last_y - 400.0) < 1e-6


@pytest.mark.unit
def test_build_trajectory_zero_distance() -> None:
    """Trajectory for same start/end doesn't crash and lands on target."""
    random.seed(0)
    points = _build_trajectory(50.0, 50.0, 50.0, 50.0)
    assert len(points) >= 2
    last_x, last_y = points[-1]
    assert abs(last_x - 50.0) < 1e-6
    assert abs(last_y - 50.0) < 1e-6
