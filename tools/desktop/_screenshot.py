"""Screenshot capture from the desktop environment.

Saves the screenshot to a file in the shared volume (host-mounted home dir)
and reads it from the host filesystem, avoiding binary-over-stdout corruption
from podman exec stream framing.
"""

import asyncio
import logging
from pathlib import Path

from config import load_config
from tools.desktop._exec import DesktopExecError, _current_display, _run_desktop_cmd

logger = logging.getLogger(__name__)


async def capture_screenshot() -> bytes:
    """Capture a screenshot of the desktop and return raw PNG bytes.

    Saves to a file in the shared volume and reads from the host to
    avoid binary corruption from podman exec stream framing.  Uses a
    per-display filename to avoid collisions between parallel agents.

    Returns:
        Raw PNG image bytes.

    Raises:
        RuntimeError: If the screenshot capture fails.
    """
    config = load_config()
    host_home = config.virtual_computer.home_dir

    # Per-agent screenshot path to avoid parallel collisions.
    display = _current_display.get() or config.desktop.user_display
    safe_display = display.replace(":", "")
    container_path = "/home/computron/.desktop_screenshot_%s.png" % safe_display

    # Use scrot to capture the screen to a file inside the shared volume
    try:
        await _run_desktop_cmd(
            "scrot -o -p %s" % container_path,
        )
    except DesktopExecError as exc:
        msg = "Screenshot capture failed: %s" % exc
        logger.error(msg)
        raise RuntimeError(msg) from exc

    # Read the file from the host filesystem (shared volume)
    host_path = Path(host_home) / (".desktop_screenshot_%s.png" % safe_display)

    loop = asyncio.get_running_loop()

    def _read_and_cleanup() -> bytes:
        if not host_path.exists():
            msg = "Screenshot file not found at %s" % host_path
            raise RuntimeError(msg)
        data = host_path.read_bytes()
        host_path.unlink(missing_ok=True)
        return data

    try:
        return await loop.run_in_executor(None, _read_and_cleanup)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Failed to read desktop screenshot")
        raise RuntimeError("Screenshot read failed: %s" % exc) from exc
