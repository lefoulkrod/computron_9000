"""Desktop agent for controlling a full GUI desktop environment.

Uses the accessibility tree to observe interactive elements, then
acts via mouse and keyboard tools using the element coordinates.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from sdk import make_run_agent_as_tool_function
from tools.desktop import (
    describe_screen,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    perform_visual_action,
    read_screen,
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
    a container. Resolution: 1280x720, origin (0,0) at top-left.

    WORKFLOW:
    1. read_screen() — get numbered interactive elements with coordinates.
    2. Act on an element using mouse_click(x, y) with its coordinates.
    3. Every action returns the updated element list — read it to decide
       the next step. Repeat until done.

    EXAMPLE:
      [1] [push button] Save — click at (120, 55)
      [2] [menu] File — click at (21, 63)
    To click Save: mouse_click(120, 55)

    CHOOSING THE RIGHT TOOL:
    - read_screen() is fast — use it to find interactive elements.
    - describe_screen() is slow — use it when you need visual context
      beyond the element list (what an app shows, non-interactive text).
    - perform_visual_action(task) — use when the a11y tree doesn't have
      what you need (canvas, games, custom widgets, images). Sends a
      screenshot to a vision model that predicts and executes the action.
    - Prefer keyboard shortcuts when they're faster than clicking.

    XDOTOOL KEY NAMES (for keyboard_press):
        "Return", "Tab", "Escape", "BackSpace", "Delete", "space",
        "Home", "End", "Page_Up", "Page_Down",
        "Up", "Down", "Left", "Right",
        Combos: "ctrl+c", "ctrl+v", "ctrl+s", "ctrl+z", "alt+F4"

    WINDOW MANAGEMENT (via run_bash_cmd):
    Title bar buttons are NOT in the element list. Use wmctrl instead:
    - List:     run_bash_cmd("DISPLAY=:99 wmctrl -l")
    - Focus:    run_bash_cmd("DISPLAY=:99 wmctrl -a 'Title'")
    - Close:    run_bash_cmd("DISPLAY=:99 wmctrl -c 'Title'")
    - Resize:   run_bash_cmd("DISPLAY=:99 wmctrl -r 'Title' -e 0,x,y,w,h")
    - Maximize: run_bash_cmd("DISPLAY=:99 wmctrl -r 'Title' -b toggle,maximized_vert,maximized_horz")

    LAUNCHING APPS: run_bash_cmd("DISPLAY=:99 libreoffice &")
    """
)
TOOLS = [
    read_screen,
    describe_screen,
    perform_visual_action,
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
