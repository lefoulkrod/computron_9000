"""Desktop interaction tools for the desktop agent.

Provides two observation tools:
- read_screen() — fast a11y tree listing interactive elements with coordinates
- describe_screen() — vision model description of what's visible on screen

Action tools (mouse/keyboard) return the a11y tree after each action.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import shlex
from typing import cast

from ollama import AsyncClient, Image

from config import load_config
from tools.desktop._exec import _run_desktop_cmd
from tools.desktop._lifecycle import ensure_desktop_running
from tools.desktop._screenshot import capture_screenshot

logger = logging.getLogger(__name__)

# Post-action settle delay before observation
_SETTLE_DELAY_S = 2.0


async def _get_a11y_tree() -> list[dict]:
    """Get the accessibility tree from the container."""
    try:
        raw = await _run_desktop_cmd(
            "/usr/bin/python3.10 /opt/desktop/a11y_tree.py",
        )
        # Podman exec stream framing inserts 8-byte binary headers at chunk
        # boundaries (~8KB).  Strip all non-printable bytes so the JSON
        # parser sees clean text.
        cleaned = "".join(c for c in raw if c.isprintable() or c in "\n\r\t")
        start = cleaned.find("[")
        if start == -1:
            return []
        return json.loads(cleaned[start:])
    except Exception:
        logger.debug("a11y tree unavailable", exc_info=True)
        return []


def _format_a11y_tree(elements: list[dict]) -> str:
    """Format a11y elements grouped by window for the agent."""
    if not elements:
        return ""

    # Group elements by window
    groups: dict[str, list[tuple[int, dict]]] = {}
    for i, el in enumerate(elements, 1):
        window = el.get("window") or "(desktop)"
        groups.setdefault(window, []).append((i, el))

    lines = ["INTERACTIVE ELEMENTS:"]
    for window, items in groups.items():
        lines.append("  [%s]" % window)
        for i, el in items:
            cx = el["x"] + el["w"] // 2
            cy = el["y"] + el["h"] // 2
            role = el.get("role") or "unknown"
            states = el.get("states")
            state_str = " (%s)" % ", ".join(states) if states else ""
            lines.append(
                "    [%d] [%s] %s%s — click at (%d, %d)"
                % (i, role, el["label"], state_str, cx, cy),
            )
    return "\n".join(lines)


async def _observe() -> str:
    """Capture the accessibility tree as the desktop observation.

    Returns a numbered list of interactive elements the agent can use
    to decide actions. Each element has a role, label, and click coords.
    """
    a11y_elements = await _get_a11y_tree()
    observation = _format_a11y_tree(a11y_elements) or "(no interactive elements found)"
    logger.info("observe: %s", observation[:500])
    return observation


async def read_screen() -> str:
    """Read the interactive elements currently visible on the desktop.

    Returns a numbered list of interactive elements (buttons, menus,
    text fields, etc.) with their roles, labels, and click coordinates
    from the accessibility tree.

    Returns:
        Numbered element list the agent can use to decide actions.
    """
    await ensure_desktop_running()
    return await _observe()


_DESCRIBE_PROMPT = (
    "Describe this desktop screenshot precisely. "
    "List every window visible with its title and whether it is active. "
    "List all readable text, UI elements, buttons, menus, toolbars, "
    "dialog boxes, and the taskbar contents. "
    "Be specific and exhaustive — an AI agent needs this to understand "
    "what is on screen beyond the interactive elements."
)


async def describe_screen() -> str:
    """Get a vision model description of what is visible on the desktop.

    Captures a screenshot and sends it to a vision model for a detailed
    text description. Use this when you need to understand visual context
    beyond the interactive element list from read_screen().

    Returns:
        Text description of the desktop from the vision model.
    """
    await ensure_desktop_running()

    cfg = load_config()
    if cfg.desktop.vision_model is None:
        return "Error: No desktop vision model configured (desktop.vision_model)."

    try:
        screenshot_bytes = await capture_screenshot()
    except RuntimeError as exc:
        logger.exception("Failed to capture screenshot for describe_screen")
        return "Error: Failed to capture screenshot: %s" % exc

    encoded = base64.b64encode(screenshot_bytes).decode("ascii")
    host = getattr(getattr(cfg, "llm", None), "host", None)
    client = AsyncClient(host=host) if host else AsyncClient()

    try:
        response = await client.chat(
            model=cfg.desktop.vision_model,
            messages=[{
                "role": "user",
                "content": _DESCRIBE_PROMPT,
                "images": [Image(value=encoded)],
            }],
            options={"temperature": 0.1, "num_predict": 2048},
            think=False,
        )
    except Exception as exc:
        logger.exception("Vision model failed for describe_screen")
        return "Error: Vision model failed: %s" % exc

    msg = response.get("message", {})
    if isinstance(msg, dict):
        answer = msg.get("content", "")
    else:
        answer = cast(str, getattr(msg, "content", ""))

    if not answer:
        return "Error: Vision model returned an empty response."

    return answer



async def mouse_click(x: int, y: int, button: str = "left") -> str:
    """Click at the specified coordinates on the desktop.

    Args:
        x: Horizontal pixel coordinate (0 = left edge).
        y: Vertical pixel coordinate (0 = top edge).
        button: Mouse button — "left", "right", or "middle".

    Returns:
        Observation of the desktop after clicking.
    """
    await ensure_desktop_running()
    button_map = {"left": "1", "middle": "2", "right": "3"}
    btn = button_map.get(button, "1")
    await _run_desktop_cmd(
        "xdotool mousemove --sync %d %d click %s" % (x, y, btn),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()


async def mouse_double_click(x: int, y: int) -> str:
    """Double-click at the specified coordinates on the desktop.

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.

    Returns:
        Observation of the desktop after double-clicking.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd(
        "xdotool mousemove --sync %d %d click --repeat 2 --delay 100 1"
        % (x, y),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()


async def mouse_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Drag from one point to another on the desktop.

    Args:
        x1: Start horizontal coordinate.
        y1: Start vertical coordinate.
        x2: End horizontal coordinate.
        y2: End vertical coordinate.

    Returns:
        Observation of the desktop after dragging.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd(
        "xdotool mousemove --sync %d %d mousedown 1 "
        "mousemove --sync %d %d mouseup 1"
        % (x1, y1, x2, y2),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()


async def keyboard_type(text: str) -> str:
    """Type text on the desktop using the clipboard.

    Uses clipboard paste (xclip + Ctrl+V) for reliable input — handles
    Unicode, special characters, and is faster than keystroke simulation.

    Args:
        text: The text to type.

    Returns:
        Observation of the desktop after typing.
    """
    await ensure_desktop_running()
    # Use xdotool type with a short delay — works universally across
    # terminals, text editors, and GUI apps. Chunk long text to avoid
    # dropped characters.
    for i in range(0, len(text), 50):
        chunk = text[i : i + 50]
        await _run_desktop_cmd(
            "xdotool type --clearmodifiers --delay 8 -- %s"
            % shlex.quote(chunk),
        )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()


async def keyboard_press(key: str) -> str:
    """Press a key or key combination on the desktop.

    Args:
        key: Key name or combo, e.g. "Return", "ctrl+c", "alt+F4",
            "ctrl+shift+s". Uses xdotool key names.

    Returns:
        Observation of the desktop after pressing the key.
    """
    await ensure_desktop_running()
    await _run_desktop_cmd("xdotool key -- %s" % key)
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()


async def scroll(x: int, y: int, direction: str = "down", clicks: int = 3) -> str:
    """Scroll the mouse wheel at the specified position.

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
        direction: Scroll direction — "up" or "down".
        clicks: Number of scroll clicks.

    Returns:
        Observation of the desktop after scrolling.
    """
    await ensure_desktop_running()
    btn = "4" if direction == "up" else "5"
    await _run_desktop_cmd(
        "xdotool mousemove --sync %d %d click --repeat %d %s"
        % (x, y, clicks, btn),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe()
