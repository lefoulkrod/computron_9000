"""Desktop tools for controlling a full GUI desktop environment.

Public API:
- read_screen, describe_screen — observation tools.
- mouse_click, mouse_double_click, mouse_drag,
  keyboard_type, keyboard_press, scroll — action tools.
- ensure_desktop_running, is_desktop_running, start_desktop, stop_desktop — lifecycle.
- capture_screenshot — raw screenshot capture.
"""

from ._lifecycle import (
    allocate_display,
    ensure_desktop_running,
    is_desktop_running,
    release_display,
    start_agent_desktop,
    start_desktop,
    stop_desktop,
)
from ._screenshot import capture_screenshot
from ._tools import (
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

__all__ = [
    "allocate_display",
    "capture_screenshot",
    "describe_screen",
    "ensure_desktop_running",
    "is_desktop_running",
    "keyboard_press",
    "keyboard_type",
    "mouse_click",
    "mouse_double_click",
    "mouse_drag",
    "perform_visual_action",
    "read_screen",
    "release_display",
    "scroll",
    "start_agent_desktop",
    "start_desktop",
    "stop_desktop",
]
