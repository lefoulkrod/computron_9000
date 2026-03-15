"""Desktop agent for controlling a full GUI desktop environment.

Uses a screenshot-analyze-act loop to interact with any graphical
application running in the container's Xfce4 desktop.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from sdk import make_run_agent_as_tool_function
from tools.desktop import (
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    screenshot,
    scroll,
)
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

NAME = "DESKTOP_AGENT"
DESCRIPTION = (
    "Control a full Ubuntu desktop (Xfce4) with mouse and keyboard. "
    "For GUI applications like LibreOffice, GIMP, file managers, or "
    "anything that needs a graphical interface beyond the web browser."
)
SYSTEM_PROMPT = dedent(
    """\
    You are DESKTOP_AGENT, controlling a full Ubuntu Xfce4 desktop inside
    a container. You interact via a screenshot-analyze-act loop.

    WORKFLOW:
    1. Call screenshot() to observe the current desktop state.
    2. Analyze the text description to understand what's on screen.
    3. Decide which action to take (click, type, press key, etc.).
    4. Execute the action — each action automatically takes a new
       screenshot and returns a description of the result.
    5. Repeat until the task is complete.

    COORDINATE SYSTEM:
    - Resolution: 1280x720 pixels
    - Origin: (0, 0) at top-left corner
    - X increases rightward, Y increases downward
    - Be precise with coordinates based on the vision model's descriptions.

    MOUSE TOOLS:
    - mouse_click(x, y, button="left") — single click
    - mouse_double_click(x, y) — double click (open files, select words)
    - mouse_drag(x1, y1, x2, y2) — click-and-drag (select, move, resize)
    - scroll(x, y, direction="down", clicks=3) — scroll wheel

    KEYBOARD TOOLS:
    - keyboard_type(text) — type text at the current cursor position
    - keyboard_press(key) — press a key or combo:
        Single keys: "Return", "Tab", "Escape", "BackSpace", "Delete",
                     "space", "Home", "End", "Page_Up", "Page_Down"
        Arrow keys:  "Up", "Down", "Left", "Right"
        Combos:      "ctrl+c", "ctrl+v", "ctrl+s", "ctrl+z", "alt+F4",
                     "ctrl+shift+s", "super" (open app menu)

    LAUNCHING APPS:
    - Use run_bash_cmd to launch GUI apps: run_bash_cmd("DISPLAY=:1 libreoffice &")
    - Or click the application menu in the taskbar.

    EFFICIENCY:
    - Start with screenshot() to see what's on screen.
    - Use keyboard shortcuts when possible (ctrl+s to save, ctrl+c to copy).
    - After actions, read the description carefully before the next step.
    - If an action didn't work, try a slightly different approach.
    """
)
TOOLS = [
    screenshot,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    keyboard_type,
    keyboard_press,
    scroll,
    run_bash_cmd,
]

desktop_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "desktop_agent_tool",
]
