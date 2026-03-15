"""Desktop environment lifecycle management.

The desktop starts automatically with the container via entrypoint.sh.
These functions verify it's running and notify the UI.
"""

import asyncio
import logging

from config import load_config
from sdk.events import AssistantResponse, publish_event
from sdk.events._models import DesktopActivePayload
from tools.desktop._exec import DesktopExecError, _run_desktop_cmd

logger = logging.getLogger(__name__)

_STARTUP_TIMEOUT_S = 15
_POLL_INTERVAL_S = 0.5

def _notify_ui() -> None:
    """Emit DesktopActivePayload to show the noVNC panel in the UI."""
    config = load_config()
    publish_event(AssistantResponse(
        event=DesktopActivePayload(
            type="desktop_active",
            resolution=config.desktop.resolution,
        ),
    ))


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
