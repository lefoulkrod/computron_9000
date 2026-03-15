"""Desktop interaction tools for the desktop agent.

Each tool follows a screenshot-ground-act pattern: execute an action,
capture a screenshot, send it to the grounding model, and return the
result.
"""

from __future__ import annotations

import asyncio
import logging
import shlex

from tools.desktop._exec import _run_desktop_cmd
from tools.desktop._ground import _run_grounding
from tools.desktop._lifecycle import ensure_desktop_running
from tools.desktop._screenshot import capture_screenshot

logger = logging.getLogger(__name__)

# Post-action settle delay before screenshot. OSWorld uses 2s flat for all
# actions — crude but proven reliable across many desktop applications.
_SETTLE_DELAY_S = 2.0

# xdotool type: chunk size and inter-key delay (ms). Chunking avoids
# dropped characters on long inputs. Values from OSWorld.
_TYPING_GROUP_SIZE = 50
_TYPING_DELAY_MS = 12

_DESCRIBE_TASK = (
    "Describe what is visible on the desktop. Include window titles, "
    "button labels, menu items, text content, and their approximate "
    "positions. Be precise about UI element locations."
)


async def screenshot() -> str:
    """Observe the current state of the desktop.

    Takes a screenshot and returns a text description of what is visible,
    including window titles, button labels, menu items, and text content
    with their approximate positions.

    Returns:
        Text description of the desktop from the vision model.
    """
    await ensure_desktop_running()
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    description = result.get("thought", "") or result.get("raw", "")
    logger.info("screenshot() response: %s", description[:500])
    return description


async def ground(task: str) -> str:
    """Find a UI element and determine the next action using vision.

    Takes a screenshot, sends it to the grounding model with the task
    description, and returns the recommended action with precise
    coordinates.

    Args:
        task: What you want to do, e.g. "Click the Save button",
            "Open the Documents folder", "Close the calculator".

    Returns:
        The grounding model's recommended action with coordinates.
    """
    await ensure_desktop_running()
    # capture_screenshot() saves the file to the shared volume;
    # _run_grounding() reads it from inside the container.
    await capture_screenshot()
    result = await _run_grounding(task)
    logger.info("ground(%s) response: %s", task, result)

    lines = []
    thought = result.get("thought", "")
    if thought:
        lines.append("Thought: %s" % thought)

    action_type = result.get("action_type", "unknown")
    if action_type == "click" and "x" in result:
        lines.append("Action: click at (%d, %d)" % (result["x"], result["y"]))
    elif action_type == "left_double" and "x" in result:
        lines.append("Action: double-click at (%d, %d)" % (result["x"], result["y"]))
    elif action_type == "type" and "type_content" in result:
        lines.append("Action: type '%s'" % result["type_content"])
    elif action_type == "hotkey" and "hotkey" in result:
        lines.append("Action: press %s" % result["hotkey"])
    elif action_type == "scroll":
        direction = result.get("scroll_direction", "down")
        if "x" in result:
            lines.append("Action: scroll %s at (%d, %d)" % (direction, result["x"], result["y"]))
        else:
            lines.append("Action: scroll %s" % direction)
    elif action_type == "wait":
        lines.append("Action: wait")
    elif action_type == "finished":
        content = result.get("finished_content", "")
        lines.append("Action: finished — %s" % content if content else "Action: finished")
    else:
        lines.append("Action: %s" % result.get("action", "unknown"))

    return "\n".join(lines)


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
    await _run_desktop_cmd(
        "xdotool mousemove --sync %d %d click %s" % (x, y, btn),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")


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
        "xdotool mousemove --sync %d %d click --repeat 2 --delay 500 1"
        % (x, y),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")


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
        "xdotool mousemove --sync %d %d mousedown 1 "
        "mousemove --sync %d %d mouseup 1"
        % (x1, y1, x2, y2),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")


async def keyboard_type(text: str) -> str:
    """Type text on the desktop using the keyboard.

    Args:
        text: The text to type.

    Returns:
        Text description of the desktop after typing.
    """
    await ensure_desktop_running()
    # Chunk long text to avoid dropped characters (OSWorld pattern).
    # Each chunk is shell-quoted for safety.
    for i in range(0, len(text), _TYPING_GROUP_SIZE):
        chunk = text[i : i + _TYPING_GROUP_SIZE]
        await _run_desktop_cmd(
            "xdotool type --delay %d --clearmodifiers -- %s"
            % (_TYPING_DELAY_MS, shlex.quote(chunk)),
        )
    await asyncio.sleep(_SETTLE_DELAY_S)
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")


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
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")


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
        "xdotool mousemove --sync %d %d click --repeat %d %s"
        % (x, y, clicks, btn),
    )
    await asyncio.sleep(_SETTLE_DELAY_S)
    await capture_screenshot()
    result = await _run_grounding(_DESCRIBE_TASK)
    return result.get("thought", "") or result.get("raw", "")
