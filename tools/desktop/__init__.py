"""Desktop tools for controlling a full GUI desktop environment.

Public API:
- screenshot, mouse_click, mouse_double_click, mouse_drag,
  keyboard_type, keyboard_press, scroll — desktop interaction tools.
- ensure_desktop_running, is_desktop_running, stop_desktop — lifecycle.
- capture_screenshot — raw screenshot capture.
"""

from ._lifecycle import ensure_desktop_running, is_desktop_running, stop_desktop
from ._screenshot import capture_screenshot
from ._tools import (
    ground,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    screenshot,
    scroll,
)

__all__ = [
    "capture_screenshot",
    "ensure_desktop_running",
    "ground",
    "is_desktop_running",
    "keyboard_press",
    "keyboard_type",
    "mouse_click",
    "mouse_double_click",
    "mouse_drag",
    "screenshot",
    "scroll",
    "stop_desktop",
]
