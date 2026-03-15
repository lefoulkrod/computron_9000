"""Vision-based grounding for desktop UI elements.

Uses UI-TARS running in the container's grounding server to locate
elements and determine actions from screenshots.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import load_config

logger = logging.getLogger(__name__)

_SCREENSHOT_FILENAME = ".desktop_screenshot.png"


async def _run_grounding(task: str) -> dict:
    """Send a grounding request to the in-container grounding server.

    Reads the screenshot from the shared volume file that
    ``capture_screenshot()`` already wrote and forwards it to the
    shared grounding client.
    """
    from tools._grounding import run_grounding

    cfg = load_config()
    host_path = Path(cfg.inference_container.home_dir) / _SCREENSHOT_FILENAME
    screenshot_bytes = host_path.read_bytes()

    response = await run_grounding(
        screenshot_bytes,
        task,
        screenshot_filename=_SCREENSHOT_FILENAME,
    )
    return response.raw
