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
from typing import TYPE_CHECKING, cast

from ollama import AsyncClient, Image

if TYPE_CHECKING:
    from rich.console import Console

    from tools._grounding import GroundingResponse

from config import load_config
from tools.desktop._exec import _run_desktop_cmd
from tools.desktop._lifecycle import ensure_desktop_running
from tools.desktop._screenshot import capture_screenshot

logger = logging.getLogger(__name__)

# Post-action settle delay before observation
_SETTLE_DELAY_S = 2.0

# Lazy-initialised Rich console for panel logging.
_console: Console | None = None


def _get_console() -> Console:
    global _console  # noqa: PLW0603
    if _console is None:
        from rich.console import Console
        _console = Console(stderr=True)
    return _console


def _log_desktop_panel(
    tool_name: str,
    *,
    elements: list[dict],
    args: str = "",
    elapsed_ms: float = 0,
) -> None:
    """Emit a Rich panel summarising a desktop tool call and its observation."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    from rich.panel import Panel
    from rich.text import Text

    body = Text()

    if not elements:
        body.append("(no interactive elements found)", style="dim italic")
    else:
        # Group elements by window, matching _format_a11y_tree layout.
        groups: dict[str, list[tuple[int, dict]]] = {}
        for i, el in enumerate(elements, 1):
            window = el.get("window") or "(desktop)"
            groups.setdefault(window, []).append((i, el))

        for window, items in groups.items():
            body.append("[%s]\n" % window, style="bold")
            for i, el in items:
                cx = el["x"] + el["w"] // 2
                cy = el["y"] + el["h"] // 2
                role = el.get("role") or "unknown"
                label = el.get("label") or ""
                states = el.get("states")
                state_str = " (%s)" % ", ".join(states) if states else ""

                body.append("  [%d] " % i, style="bold cyan")
                body.append("[%s] " % role, style="dim")
                body.append(label + state_str)
                body.append(" @ (%d, %d)\n" % (cx, cy), style="dim")

    title_parts = ["[bold cyan]%s[/bold cyan]" % tool_name]
    if args:
        title_parts.append("[dim]%s[/dim]" % args)
    title = "  ".join(title_parts)

    subtitle_parts = []
    if elapsed_ms > 0:
        subtitle_parts.append("[bold]%.0fms[/bold]" % elapsed_ms)
    subtitle_parts.append("%d elements" % len(elements))
    subtitle = "  ".join(subtitle_parts)

    _get_console().print(Panel(
        body,
        title=title,
        subtitle=subtitle,
        border_style="dim",
        expand=False,
    ))


async def _get_a11y_tree() -> list[dict]:
    """Get the accessibility tree from the container."""
    try:
        raw = await _run_desktop_cmd(
            "/usr/bin/python3.10 /opt/desktop/a11y_tree.py",
        )
        start = raw.find("[")
        if start == -1:
            return []
        return json.loads(raw[start:])
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


async def _observe(tool_name: str = "observe", args: str = "") -> str:
    """Capture the accessibility tree as the desktop observation."""
    t0 = asyncio.get_event_loop().time()
    a11y_elements = await _get_a11y_tree()
    elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
    observation = _format_a11y_tree(a11y_elements) or "(no interactive elements found)"
    _log_desktop_panel(
        tool_name, elements=a11y_elements, args=args, elapsed_ms=elapsed_ms,
    )
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
    return await _observe("read_screen")


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
    return await _observe("mouse_click", args="x=%d, y=%d, button=%s" % (x, y, button))


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
    return await _observe("mouse_double_click", args="x=%d, y=%d" % (x, y))


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
    return await _observe(
        "mouse_drag", args="(%d,%d) -> (%d,%d)" % (x1, y1, x2, y2),
    )


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
    preview = text if len(text) <= 40 else text[:37] + "..."
    return await _observe("keyboard_type", args=repr(preview))


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
    return await _observe("keyboard_press", args=key)


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
    return await _observe(
        "scroll", args="x=%d, y=%d, %s, clicks=%d" % (x, y, direction, clicks),
    )


# ── Hotkey name mapping (UI-TARS → xdotool) ─────────────────────────

_HOTKEY_MAP: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "meta": "super",
    "win": "super",
    "cmd": "super",
    "command": "super",
    "super": "super",
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "home": "Home",
    "end": "End",
}


def _normalize_hotkey_xdotool(tars_key: str) -> str:
    """Convert a UI-TARS hotkey string to xdotool format."""
    parts = tars_key.split("+")
    normalized: list[str] = []
    for part in parts:
        stripped = part.strip()
        mapped = _HOTKEY_MAP.get(stripped.lower())
        normalized.append(mapped if mapped is not None else stripped)
    return "+".join(normalized)


async def _execute_desktop_action(
    response: GroundingResponse,
) -> str:
    """Dispatch a grounding response to the appropriate desktop action."""
    action = response.action_type

    if action == "click":
        x, y = _require_desktop_coords(response)
        await _run_desktop_cmd(
            "xdotool mousemove --sync %d %d click 1" % (x, y),
        )
        return "click at (%d, %d)" % (x, y)

    if action == "left_double":
        x, y = _require_desktop_coords(response)
        await _run_desktop_cmd(
            "xdotool mousemove --sync %d %d click --repeat 2 --delay 100 1"
            % (x, y),
        )
        return "double-click at (%d, %d)" % (x, y)

    if action == "right_single":
        x, y = _require_desktop_coords(response)
        await _run_desktop_cmd(
            "xdotool mousemove --sync %d %d click 3" % (x, y),
        )
        return "right-click at (%d, %d)" % (x, y)

    if action == "drag":
        coords = response.raw.get("coordinates", [])
        if len(coords) < 2:
            return "drag failed: need two coordinate pairs"
        src = coords[0]["screen"]
        dst = coords[1]["screen"]
        await _run_desktop_cmd(
            "xdotool mousemove --sync %d %d mousedown 1 "
            "mousemove --sync %d %d mouseup 1"
            % (src[0], src[1], dst[0], dst[1]),
        )
        return "drag (%d,%d) -> (%d,%d)" % (src[0], src[1], dst[0], dst[1])

    if action == "type":
        content = response.raw.get("type_content", "")
        if content:
            for i in range(0, len(content), 50):
                chunk = content[i : i + 50]
                await _run_desktop_cmd(
                    "xdotool type --clearmodifiers --delay 8 -- %s"
                    % shlex.quote(chunk),
                )
        return "typed %r" % (content[:40] if len(content) > 40 else content)

    if action == "hotkey":
        raw_key = response.raw.get("hotkey", "")
        if not raw_key:
            return "hotkey failed: missing key"
        normalized = _normalize_hotkey_xdotool(raw_key)
        await _run_desktop_cmd("xdotool key -- %s" % normalized)
        return "hotkey %s" % normalized

    if action == "scroll":
        direction = response.raw.get("scroll_direction", "down")
        x, y = response.x or 640, response.y or 360
        btn = "4" if direction == "up" else "5"
        await _run_desktop_cmd(
            "xdotool mousemove --sync %d %d click --repeat 3 %s"
            % (x, y, btn),
        )
        return "scroll %s at (%d, %d)" % (direction, x, y)

    if action == "wait":
        await asyncio.sleep(1.0)
        return "waited 1s"

    if action == "finished":
        return "finished"

    logger.warning("Unsupported grounding action: %s", action)
    return "unsupported action: %s" % action


def _require_desktop_coords(response: GroundingResponse) -> tuple[int, int]:
    """Extract x, y from response, raising if absent."""
    if response.x is None or response.y is None:
        msg = "Action '%s' requires coordinates but none returned" % response.action_type
        raise RuntimeError(msg)
    return response.x, response.y


async def perform_visual_action(task: str) -> str:
    """Ask a vision model to decide and execute the next GUI action.

    Captures a screenshot, sends it to the UI-TARS grounding model which
    predicts the best action (click, type, scroll, etc.) and coordinates,
    then executes that action on the desktop.

    Use this when the accessibility tree doesn't have what you need — for
    example, interacting with canvas elements, games, images, or custom
    UI widgets that don't expose accessibility information.

    Args:
        task: Natural-language description of what to do, e.g.
            ``"Click the Start Game button"``,
            ``"Type hello into the search box"``, or
            ``"Scroll down to see more content"``.

    Returns:
        Observation of the desktop after executing the action.
    """
    from tools._grounding import run_grounding

    await ensure_desktop_running()

    clean_task = task.strip()
    if not clean_task:
        return "Error: task must be a non-empty string."

    # Capture the desktop screenshot.
    try:
        screenshot_bytes = await capture_screenshot()
    except RuntimeError as exc:
        logger.error("Screenshot capture failed for visual action: %s", exc)
        return "Error: Failed to capture screenshot: %s" % exc

    # Send to UI-TARS grounding server.
    try:
        response = await run_grounding(
            screenshot_bytes,
            clean_task,
            screenshot_filename="desktop_visual_action.png",
        )
    except RuntimeError as exc:
        logger.error("Grounding request failed for %r: %s", clean_task, exc)
        return "Error: Grounding request failed: %s" % exc

    _log_visual_action_panel(clean_task, response)

    # Handle "finished" — no action needed.
    if response.action_type == "finished":
        finished_content = response.raw.get("finished_content", "")
        obs = await _observe("perform_visual_action", args="finished")
        if finished_content:
            return obs + "\n\n--- Vision model says task is finished: %s ---" % finished_content
        return obs

    # Execute the predicted action.
    try:
        action_desc = await _execute_desktop_action(response)
    except RuntimeError as exc:
        logger.error("Visual action execution failed: %s", exc)
        return "Error: Action execution failed: %s" % exc

    await asyncio.sleep(_SETTLE_DELAY_S)
    return await _observe(
        "perform_visual_action", args="%s → %s" % (clean_task[:50], action_desc),
    )


def _log_visual_action_panel(task: str, response: GroundingResponse) -> None:
    """Emit a Rich panel summarising the grounding model prediction."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    from rich.panel import Panel
    from rich.text import Text

    body = Text()
    body.append("Task: ", style="bold")
    body.append(task + "\n")
    body.append("Thought: ", style="bold")
    body.append((response.thought or "(none)") + "\n", style="italic")
    body.append("Action: ", style="bold")
    body.append(response.action_type, style="bold green")

    if response.x is not None and response.y is not None:
        body.append(" at (%d, %d)" % (response.x, response.y), style="cyan")

    # Show extra fields for type/hotkey/scroll.
    extra = response.raw.get("type_content") or response.raw.get("hotkey") or ""
    if extra:
        body.append("\nContent: ", style="bold")
        preview = extra if len(extra) <= 60 else extra[:57] + "..."
        body.append(preview, style="dim")

    _get_console().print(Panel(
        body,
        title="[bold magenta]perform_visual_action[/bold magenta]",
        border_style="magenta",
        expand=False,
    ))
