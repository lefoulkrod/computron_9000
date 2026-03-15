"""Walk the AT-SPI accessibility tree and return visible interactive elements.

Runs inside the container. Outputs JSON to stdout.
Requires: python3-pyatspi2, at-spi2-core, libatk-adaptor
"""

import json
import re
import sys

import pyatspi

# Roles considered interactive
_INTERACTIVE_ROLES = frozenset({
    pyatspi.ROLE_PUSH_BUTTON,
    pyatspi.ROLE_TOGGLE_BUTTON,
    pyatspi.ROLE_RADIO_BUTTON,
    pyatspi.ROLE_CHECK_BOX,
    pyatspi.ROLE_MENU,
    pyatspi.ROLE_MENU_ITEM,
    pyatspi.ROLE_MENU_BAR,
    pyatspi.ROLE_CHECK_MENU_ITEM,
    pyatspi.ROLE_RADIO_MENU_ITEM,
    pyatspi.ROLE_COMBO_BOX,
    pyatspi.ROLE_LIST_ITEM,
    pyatspi.ROLE_TEXT,
    pyatspi.ROLE_PASSWORD_TEXT,
    pyatspi.ROLE_ENTRY,
    pyatspi.ROLE_SPIN_BUTTON,
    pyatspi.ROLE_SLIDER,
    pyatspi.ROLE_LINK,
    pyatspi.ROLE_PAGE_TAB,
    pyatspi.ROLE_TOOL_BAR,
    pyatspi.ROLE_TREE_ITEM,
    pyatspi.ROLE_TABLE_CELL,
    pyatspi.ROLE_ICON,
})

# Labels that look like icon theme names — not useful for the agent
_ICON_NOISE_RE = re.compile(
    r"-symbolic$|^gtk-|^edit-|^view-|^dialog-|^document-|^go-|^list-"
    r"|^window-|^process-|^mail-|^media-|^system-|^folder-|^user-"
    r"|^network-|^preferences-|^application-|^emblem-|^action-"
)

# States worth surfacing to the agent
_AGENT_VISIBLE_STATES = {
    pyatspi.STATE_FOCUSED: "focused",
    pyatspi.STATE_CHECKED: "checked",
    pyatspi.STATE_SELECTED: "selected",
    pyatspi.STATE_EXPANDED: "expanded",
    pyatspi.STATE_PRESSED: "pressed",
    pyatspi.STATE_EDITABLE: "editable",
}

_WINDOW_ROLES = frozenset({
    pyatspi.ROLE_FRAME,
    pyatspi.ROLE_DIALOG,
    pyatspi.ROLE_WINDOW,
})

_MAX_DEPTH = 30


def _get_window_ancestor(accessible):
    """Walk up to find the nearest frame/dialog/window ancestor.

    Returns (name, x_position) tuple, or (None, None) if not found.
    The x_position is used to disambiguate windows with identical names.
    """
    current = accessible
    for _ in range(50):
        try:
            current = current.parent
            if current is None:
                return None, None
            if current.getRole() in _WINDOW_ROLES:
                name = current.name or None
                extents = _get_extents(current)
                x_pos = extents[0] if extents else 0
                return name, x_pos
        except Exception:
            return None, None
    return None, None


def _is_icon_noise(role, label):
    """Check if an element is an icon with a theme-style name."""
    if role != pyatspi.ROLE_ICON:
        return False
    return bool(_ICON_NOISE_RE.search(label))


def _is_desktop_frame(role, label, extents):
    """Check if this is the full-screen Desktop frame element."""
    if role != pyatspi.ROLE_FRAME:
        return False
    if label != "Desktop":
        return False
    # Desktop frame covers most of the screen (at least 1000x600)
    return extents[2] >= 1000 and extents[3] >= 600


def _get_text(accessible):
    try:
        ti = accessible.queryText()
        raw = ti.getText(0, ti.characterCount)
        return raw.replace("\ufffc", "").replace("\ufffd", "").strip()
    except NotImplementedError:
        return ""


def _get_extents(accessible):
    try:
        c = accessible.queryComponent()
        b = c.getExtents(pyatspi.XY_SCREEN)
        return (b.x, b.y, b.width, b.height)
    except (NotImplementedError, AttributeError):
        return None


def _walk(accessible, depth=0):
    if depth > _MAX_DEPTH:
        return

    state_set = accessible.getState()
    visible = state_set.contains(pyatspi.STATE_VISIBLE)
    showing = state_set.contains(pyatspi.STATE_SHOWING)

    if visible and showing:
        role = accessible.getRole()
        is_interactive = role in _INTERACTIVE_ROLES
        if not is_interactive:
            # Check if sensitive+focusable
            if state_set.contains(pyatspi.STATE_SENSITIVE) and state_set.contains(pyatspi.STATE_FOCUSABLE):
                is_interactive = True

        if is_interactive:
            extents = _get_extents(accessible)
            if extents and extents[2] > 0 and extents[3] > 0:
                # Skip icon-theme noise (e.g. "dialog-error-symbolic")
                if _is_icon_noise(role, accessible.name or ""):
                    pass
                # Skip full-screen Desktop frame
                elif _is_desktop_frame(role, accessible.name or "", extents):
                    pass
                else:
                    name = accessible.name or ""
                    text = _get_text(accessible)
                    role_name = accessible.getRoleName()
                    if not role_name:
                        # Infer a useful role for elements found via
                        # sensitive+focusable fallback (e.g. Xfce panel items)
                        if state_set.contains(pyatspi.STATE_CHECKABLE):
                            role_name = "toggle"
                        elif extents[1] < 30 or extents[1] > 690:
                            role_name = "panel item"
                        else:
                            role_name = "clickable"
                    label = name or text or ""
                    if label:
                        states = [
                            state_name
                            for atspi_state, state_name in _AGENT_VISIBLE_STATES.items()
                            if state_set.contains(atspi_state)
                        ]
                        win_name, win_x = _get_window_ancestor(accessible)
                        el = {
                            "role": role_name,
                            "label": label,
                            "x": extents[0],
                            "y": extents[1],
                            "w": extents[2],
                            "h": extents[3],
                        }
                        if states:
                            el["states"] = states
                        if win_name:
                            el["window"] = win_name
                        # Store window x-position for disambiguation
                        if win_x is not None:
                            el["_win_x"] = win_x
                        yield el

    try:
        for i in range(accessible.childCount):
            try:
                child = accessible[i]
                if child is not None:
                    yield from _walk(child, depth + 1)
            except Exception:
                continue
    except Exception:
        pass


def _disambiguate_windows(elements):
    """Make duplicate window names unique using position hints.

    When multiple windows share the same name, appends a position
    label based on horizontal position: "(left)", "(right)", or
    "#N" when there are more than two.
    """
    # Collect unique (window_name, win_x) pairs to detect duplicates
    window_positions = {}
    for el in elements:
        win = el.get("window")
        win_x = el.get("_win_x")
        if win and win_x is not None:
            # Track each distinct x-position per window name
            window_positions.setdefault(win, set()).add(win_x)

    # Build rename map for duplicated names
    rename_map = {}
    for win_name, x_positions in window_positions.items():
        if len(x_positions) <= 1:
            continue
        sorted_positions = sorted(x_positions)
        if len(sorted_positions) == 2:
            # Use left/right labels
            rename_map[(win_name, sorted_positions[0])] = "%s (left)" % win_name
            rename_map[(win_name, sorted_positions[1])] = "%s (right)" % win_name
        else:
            # Use numbered labels sorted by position
            for idx, x_pos in enumerate(sorted_positions, 1):
                rename_map[(win_name, x_pos)] = "%s #%d" % (win_name, idx)

    # Apply renames and strip internal _win_x field
    for el in elements:
        win = el.get("window")
        win_x = el.pop("_win_x", None)
        if win and win_x is not None:
            key = (win, win_x)
            if key in rename_map:
                el["window"] = rename_map[key]

    return elements


def main():
    desktop = pyatspi.Registry.getDesktop(0)
    elements = []
    for i in range(desktop.childCount):
        try:
            app = desktop[i]
            if app is not None:
                elements.extend(_walk(app, depth=1))
        except Exception:
            continue
    elements = _disambiguate_windows(elements)
    print(json.dumps(elements))


if __name__ == "__main__":
    main()
