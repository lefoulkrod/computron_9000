"""Desktop interaction tools for the desktop agent.

Each tool follows the screenshot-analyze-act pattern: execute an action,
capture a screenshot, send it to the vision model, and return the text
description.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import cast

from ollama import AsyncClient, Image

from config import load_config
from tools.desktop._exec import _run_desktop_cmd
from tools.desktop._lifecycle import ensure_desktop_running
from tools.desktop._screenshot import capture_screenshot

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "Describe what is visible on the desktop. Include window titles, "
    "button labels, menu items, text content, and their approximate "
    "positions. Be precise about UI element locations."
)

# Settle time after an action before capturing screenshot (ms)
_SETTLE_DELAY_S = 0.2


async def _describe_desktop() -> str:
    """Capture a screenshot and send it to the vision model for description."""
    screenshot_bytes = await capture_screenshot()
    encoded = base64.b64encode(screenshot_bytes).decode("ascii")

    cfg = load_config()
    if cfg.vision is None:
        return "Error: Vision model configuration missing."

    vision = cfg.vision
    host = cfg.llm.host if getattr(cfg, "llm", None) else None
    client = AsyncClient(host=host) if host else AsyncClient()

    try:
        response = await client.generate(
            model=vision.model,
            prompt=_VISION_PROMPT,
            options=vision.options,
            images=[Image(value=encoded)],
            think=vision.think,
        )
    except Exception as exc:
        logger.exception("Vision model failed for desktop screenshot")
        return "Error: Vision model failed: %s" % exc

    answer = cast(str | None, getattr(response, "response", None))
    if answer is None:
        return "Error: Vision model did not return a response."

    return answer


async def screenshot() -> str:
    """Observe the current state of the desktop.

    Takes a screenshot and returns a text description of what is visible,
    including window titles, button labels, menu items, and text content
    with their approximate positions.

    Returns:
        Text description of the desktop from the vision model.
    """
    await ensure_desktop_running()
    return await _describe_desktop()


async def mouse_click(x: int, y: int, button: str = "left") -> str:
    """Click at the specified coordinates on the desktop.

    Args:
        x: Horizontal pixel coordinate (0 = left edge).
        y: Vertical pixel coordinate (0 = top edge).
        button: Mouse button — "left", "right", or "middle".

    Returns:
        Text description of the desktop after clicking.
    """
    await ensure_desktop_running()
    button_map = {"left": "1", "middle": "2", "right": "3"}
    btn = button_map.get(button, "1")
    await _run_desktop_cmd("xdotool mousemove %d %d click %s" % (x, y, btn))
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()


async def mouse_double_click(x: int, y: int) -> str:
    """Double-click at the specified coordinates on the desktop.

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.

    Returns:
        Text description of the desktop after double-clicking.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd(
        "xdotool mousemove %d %d click --repeat 2 --delay 100 1" % (x, y),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()


async def mouse_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Drag from one point to another on the desktop.

    Args:
        x1: Start horizontal coordinate.
        y1: Start vertical coordinate.
        x2: End horizontal coordinate.
        y2: End vertical coordinate.

    Returns:
        Text description of the desktop after dragging.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd(
        "xdotool mousemove %d %d mousedown 1 mousemove --sync %d %d mouseup 1"
        % (x1, y1, x2, y2),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()


async def keyboard_type(text: str) -> str:
    """Type text on the desktop using the keyboard.

    Args:
        text: The text to type.

    Returns:
        Text description of the desktop after typing.
    """
    await ensure_desktop_running()
    # Use xdotool type with --clearmodifiers to avoid modifier key interference
    await _run_desktop_cmd("xdotool type --delay 50 --clearmodifiers -- %r" % text)
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()


async def keyboard_press(key: str) -> str:
    """Press a key or key combination on the desktop.

    Args:
        key: Key name or combo, e.g. "Return", "ctrl+c", "alt+F4",
            "ctrl+shift+s". Uses xdotool key names.

    Returns:
        Text description of the desktop after pressing the key.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd("xdotool key -- %s" % key)
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()


async def scroll(x: int, y: int, direction: str = "down", clicks: int = 3) -> str:
    """Scroll the mouse wheel at the specified position.

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
        direction: Scroll direction — "up" or "down".
        clicks: Number of scroll clicks.

    Returns:
        Text description of the desktop after scrolling.
    """
    await ensure_desktop_running()
    # xdotool: button 4 = scroll up, button 5 = scroll down
    btn = "4" if direction == "up" else "5"
    await _run_desktop_cmd(
        "xdotool mousemove %d %d click --repeat %d %s" % (x, y, clicks, btn),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _describe_desktop()
