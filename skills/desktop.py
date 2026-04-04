"""Desktop skill — GUI automation with mouse and keyboard."""

from textwrap import dedent

from sdk.skills import Skill
from tools.desktop import (
    describe_screen,
    desktop_shell,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    perform_visual_action,
    read_screen,
    scroll,
)

_SKILL = Skill(
    name="desktop",
    description="GUI automation — mouse, keyboard, screen reading on Ubuntu Xfce4 desktop",
    prompt=dedent("""\
        Control a full Ubuntu Xfce4 desktop inside a container.
        Resolution: 1280x720, origin (0,0) at top-left.

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
        - read_screen() — ALWAYS call this first. Returns the a11y
          element list with coordinates. This is your primary observation.
        - mouse_click(x, y) — use coordinates FROM read_screen() output.
          This is the default way to interact with standard UI elements
          (buttons, menus, text fields, checkboxes, links, tabs, etc.).
        - describe_screen() — use when you need to see non-interactive
          content (what an image shows, text in a canvas, visual layout)
          that isn't in the element list.
        - perform_visual_action(task) — use ONLY when the target is NOT
          in read_screen() output: game canvases, custom drawn widgets,
          image regions, or elements with no a11y labels. Do NOT use
          this for standard UI elements — use mouse_click instead.
        - Prefer keyboard shortcuts when they're faster than clicking.

        DECISION RULE: read_screen() first. If the element you need is in
        the list → mouse_click its coordinates. If it's NOT in the list
        (canvas, game, unlabeled widget) → perform_visual_action.

        ONE ACTION AT A TIME — never call multiple desktop tools in
        parallel. Each action changes the screen, so the next action
        depends on the result of the previous one.

        XDOTOOL KEY NAMES (for keyboard_press):
            "Return", "Tab", "Escape", "BackSpace", "Delete", "space",
            "Home", "End", "Page_Up", "Page_Down",
            "Up", "Down", "Left", "Right",
            Combos: "ctrl+c", "ctrl+v", "ctrl+s", "ctrl+z", "alt+F4"

        WINDOW MANAGEMENT (via desktop_shell):
        - List:     desktop_shell("wmctrl -l")
        - Focus:    desktop_shell("wmctrl -a 'Title'")
        - Close:    desktop_shell("wmctrl -c 'Title'")
        - Maximize: desktop_shell("wmctrl -r 'Title' -b toggle,maximized_vert,maximized_horz")

        LAUNCHING APPS — always background with &:
            desktop_shell("libreoffice &")
            desktop_shell("python /home/computron/game.py &")
        GUI apps, games, and anything with a window MUST be backgrounded.
        Then use read_screen() to interact with the running application.
    """),
    tools=[
        read_screen,
        describe_screen,
        perform_visual_action,
        mouse_click,
        mouse_double_click,
        mouse_drag,
        keyboard_type,
        keyboard_press,
        scroll,
        desktop_shell,
    ],
)
