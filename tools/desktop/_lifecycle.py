"""On-demand desktop environment lifecycle management."""

import asyncio
import logging

from config import load_config
from sdk.events import AssistantResponse, publish_event
from sdk.events._models import DesktopActivePayload
from tools.desktop._exec import DesktopExecError, _run_desktop_cmd

logger = logging.getLogger(__name__)

_STARTUP_TIMEOUT_S = 15
_POLL_INTERVAL_S = 0.5


async def is_desktop_running() -> bool:
    """Check whether the desktop environment is running in the container."""
    try:
        output = await _run_desktop_cmd("pgrep -x Xvfb || true")
        return bool(output.strip())
    except DesktopExecError:
        return False


async def ensure_desktop_running() -> None:
    """Start the desktop environment if not already running.

    Idempotent — safe to call before every tool invocation.
    On first start, emits a ``DesktopActivePayload`` event to signal
    the UI to show the noVNC panel.
    """
    if await is_desktop_running():
        return

    logger.info("Starting desktop environment in container")

    # Run start-desktop.sh in background (nohup so it survives exec detach)
    try:
        await _run_desktop_cmd(
            "nohup /opt/desktop/start-desktop.sh > /tmp/desktop.log 2>&1 &",
            user="root",
        )
    except DesktopExecError:
        logger.exception("Failed to launch start-desktop.sh")
        raise

    # Poll until VNC port is listening
    config = load_config()
    elapsed = 0.0
    while elapsed < _STARTUP_TIMEOUT_S:
        await asyncio.sleep(_POLL_INTERVAL_S)
        elapsed += _POLL_INTERVAL_S
        try:
            output = await _run_desktop_cmd(
                "ss -tln | grep :%d || true" % config.desktop.vnc_port,
            )
            if str(config.desktop.vnc_port) in output:
                logger.info("Desktop environment ready after %.1fs", elapsed)
                # Signal the UI to show the noVNC panel
                publish_event(AssistantResponse(
                    event=DesktopActivePayload(
                        type="desktop_active",
                        resolution=config.desktop.resolution,
                    ),
                ))
                return
        except DesktopExecError:
            pass

    msg = "Desktop environment did not start within %ds" % _STARTUP_TIMEOUT_S
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
