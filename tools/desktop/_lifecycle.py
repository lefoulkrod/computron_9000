"""Desktop environment lifecycle management.

The desktop starts automatically with the container via entrypoint.sh.
These functions verify it's running, start it on demand, and notify the UI.
"""

import asyncio
import logging

from config import load_config
from sdk.events import AgentEvent, publish_event
from sdk.events._models import DesktopActivePayload
from tools.desktop._exec import DesktopExecError, _current_display, _run_desktop_cmd

logger = logging.getLogger(__name__)

_STARTUP_TIMEOUT_S = 15
_POLL_INTERVAL_S = 0.5

# Display allocation for parallel desktop agents.
_active_displays: dict[str, int] = {}  # agent_id → display number
_free_displays: list[int] = []  # recycled display numbers available for reuse
_next_display_num: int | None = None  # lazily initialized from config
_display_lock = asyncio.Lock()

def _notify_ui() -> None:
    """Emit DesktopActivePayload to show the noVNC panel in the UI."""
    config = load_config()
    publish_event(AgentEvent(payload=DesktopActivePayload(
        type="desktop_active",
        resolution=config.desktop.resolution,
    )))


async def is_desktop_running() -> bool:
    """Check whether the desktop environment is fully running."""
    try:
        output = await _run_desktop_cmd(
            "pgrep -x Xvfb > /dev/null && pgrep -x x11vnc > /dev/null && echo ok || true",
        )
        result = output.strip().endswith("ok")
        if not result:
            logger.debug("is_desktop_running: got %r", output.strip())
        return result
    except DesktopExecError as exc:
        logger.debug("is_desktop_running: exec error: %s", exc)
        return False


async def ensure_desktop_running() -> None:
    """Wait for the desktop environment to be ready and notify the UI.

    The desktop starts automatically with the container. This function
    polls until it's up, then emits a DesktopActivePayload event.
    """
    if await is_desktop_running():
        _notify_ui()
        return

    # Desktop should be starting via entrypoint — just wait for it
    logger.info("Waiting for desktop environment to be ready")
    elapsed = 0.0
    last_error = None
    while elapsed < _STARTUP_TIMEOUT_S:
        await asyncio.sleep(_POLL_INTERVAL_S)
        elapsed += _POLL_INTERVAL_S
        try:
            output = await _run_desktop_cmd(
                "pgrep -x Xvfb > /dev/null && pgrep -x x11vnc > /dev/null && echo ok || echo waiting",
            )
            result = output.strip()
            logger.debug("Desktop check at %.1fs: %s", elapsed, result)
            if result.endswith("ok"):
                logger.info("Desktop environment ready after %.1fs", elapsed)
                _notify_ui()
                return
        except DesktopExecError as exc:
            last_error = str(exc)
            logger.debug("Desktop check at %.1fs failed: %s", elapsed, exc)

    msg = "Desktop environment not ready within %ds" % _STARTUP_TIMEOUT_S
    if last_error:
        msg += " (last error: %s)" % last_error
    logger.error(msg)
    raise DesktopExecError(msg)


def _build_desktop_cmd(
    display: str, resolution: str, vnc_port: int, ws_port: int,
) -> str:
    """Build the shell command to start a desktop environment on the given display."""
    return (
        "export DISPLAY=%s;"
        " Xvfb %s -screen 0 %sx24 -ac &"
        " sleep 1;"
        " eval $(dbus-launch --sh-syntax);"
        " export GTK_MODULES=gail:atk-bridge ACCESSIBILITY_ENABLED=1;"
        " startxfce4 &"
        " sleep 2;"
        " xset s off -dpms 2>/dev/null || true;"
        " xsetroot -cursor_name left_ptr 2>/dev/null || true;"
        " x11vnc -display %s -forever -nopw -listen 0.0.0.0 -rfbport %d -shared -cursor arrow -bg;"
        " websockify --web /usr/share/novnc 0.0.0.0:%d localhost:%d &"
        " echo started"
        % (display, display, resolution, display, vnc_port, ws_port, vnc_port)
    )


def _build_start_desktop_cmd() -> str:
    """Build the shell command to start the user's desktop environment."""
    config = load_config()
    return _build_desktop_cmd(
        display=config.desktop.user_display,
        resolution=config.desktop.resolution,
        vnc_port=5900,
        ws_port=6080,
    )


async def start_desktop() -> None:
    """Start the desktop processes if not already running.

    Launches Xvfb, Xfce4, x11vnc, and websockify inside the container,
    then polls until everything is up.

    Raises:
        DesktopExecError: If the container is unreachable or startup fails.
    """
    if await is_desktop_running():
        return

    logger.info("Starting desktop environment")
    await _run_desktop_cmd(_build_start_desktop_cmd(), user="root")

    # Poll until the processes are up
    elapsed = 0.0
    while elapsed < _STARTUP_TIMEOUT_S:
        await asyncio.sleep(_POLL_INTERVAL_S)
        elapsed += _POLL_INTERVAL_S
        if await is_desktop_running():
            logger.info("Desktop environment started after %.1fs", elapsed)
            return

    raise DesktopExecError(
        "Desktop processes did not come up within %ds" % _STARTUP_TIMEOUT_S
    )


async def stop_desktop() -> None:
    """Stop the desktop environment processes in the container."""
    try:
        await _run_desktop_cmd(
            "pkill -f websockify; pkill -f x11vnc; pkill -f startxfce4; pkill -f Xvfb; true",
            user="root",
        )
        logger.info("Desktop environment stopped")
    except DesktopExecError:
        logger.exception("Failed to stop desktop environment")
        raise


async def allocate_display(agent_id: str) -> tuple[str, int]:
    """Allocate a virtual display for a desktop agent and set the ContextVar.

    Returns ``(display_str, display_num)`` — e.g. ``(":100", 100)``.
    The ContextVar is set so that all subsequent ``_run_desktop_cmd`` calls
    in this async context automatically use the allocated display.
    """
    global _next_display_num
    config = load_config()

    async with _display_lock:
        if agent_id in _active_displays:
            display_num = _active_displays[agent_id]
        else:
            if _free_displays:
                display_num = _free_displays.pop()
            else:
                if _next_display_num is None:
                    _next_display_num = config.desktop.agent_display_base
                display_num = _next_display_num
                _next_display_num += 1
            _active_displays[agent_id] = display_num

    display = ":%d" % display_num
    _current_display.set(display)
    logger.info("Allocated display %s for agent '%s'", display, agent_id)
    return display, display_num


async def release_display(agent_id: str) -> None:
    """Release the virtual display allocated to an agent.

    Stops the Xvfb and related processes for that display, then removes
    the allocation and returns the display number to the free pool.
    """
    async with _display_lock:
        display_num = _active_displays.pop(agent_id, None)
        if display_num is not None:
            _free_displays.append(display_num)
    if display_num is None:
        return

    display = ":%d" % display_num
    vnc_port = 5900 + (display_num - 99)
    try:
        await _run_desktop_cmd(
            "pkill -f 'Xvfb %s' || true;"
            " pkill -f 'x11vnc -display %s' || true;"
            " pkill -f 'websockify.*%d' || true"
            % (display, display, vnc_port),
            display=display,
            user="root",
        )
        logger.info("Released display %s for agent '%s'", display, agent_id)
    except DesktopExecError:
        logger.warning("Failed to clean up display %s for agent '%s'", display, agent_id)


async def start_agent_desktop(agent_id: str) -> str:
    """Allocate a display and start a full desktop environment on it.

    Returns the display string.  On failure the allocated display is
    released so the number can be recycled.
    """
    display, display_num = await allocate_display(agent_id)
    config = load_config()
    vnc_port = 5900 + (display_num - 99)
    ws_port = config.desktop.websocket_port + (display_num - 99)

    try:
        start_cmd = _build_desktop_cmd(display, config.desktop.resolution, vnc_port, ws_port)
        await _run_desktop_cmd(start_cmd, display=display, user="root")

        # Poll until ready
        elapsed = 0.0
        while elapsed < _STARTUP_TIMEOUT_S:
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S
            try:
                output = await _run_desktop_cmd(
                    "pgrep -f 'Xvfb %s' > /dev/null && echo ok || true" % display,
                    display=display,
                )
                if output.strip().endswith("ok"):
                    logger.info("Agent desktop %s ready after %.1fs", display, elapsed)
                    return display
            except DesktopExecError:
                pass

        raise DesktopExecError(
            "Agent desktop %s did not start within %ds" % (display, _STARTUP_TIMEOUT_S)
        )
    except Exception:
        # Clean up the allocated display on any failure
        await release_display(agent_id)
        raise
