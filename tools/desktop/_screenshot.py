"""Screenshot capture from the desktop environment."""

import logging
from pathlib import Path

from config import load_config
from tools.desktop._exec import DesktopExecError, _current_display, _run_desktop_cmd

logger = logging.getLogger(__name__)


async def capture_screenshot() -> bytes:
    """Capture a screenshot of the desktop and return raw PNG bytes.

    Uses a per-display filename to avoid collisions between parallel agents.

    Returns:
        Raw PNG image bytes.

    Raises:
        RuntimeError: If the screenshot capture fails.
    """
    config = load_config()

    # Per-agent screenshot path to avoid parallel collisions.
    display = _current_display.get() or config.desktop.user_display
    safe_display = display.replace(":", "")
    screenshot_path = "/tmp/.desktop_screenshot_%s.png" % safe_display

    try:
        await _run_desktop_cmd("scrot -o -p %s" % screenshot_path)
    except DesktopExecError as exc:
        msg = "Screenshot capture failed: %s" % exc
        logger.error(msg)
        raise RuntimeError(msg) from exc

    path = Path(screenshot_path)
    if not path.exists():
        msg = "Screenshot file not found at %s" % screenshot_path
        raise RuntimeError(msg)

    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data
