"""Vision-based grounding for desktop UI elements.

Uses UI-TARS running in the container's grounding server to locate
elements and determine actions from screenshots.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from config import load_config

logger = logging.getLogger(__name__)

# First launch may need to download model weights (~31GB) + load into VRAM.
# Subsequent calls are fast (~5s inference).
_REQUEST_TIMEOUT = 1860.0  # 31 minutes — covers first-time download + startup

# The screenshot is already saved to this path by capture_screenshot().
# We read it from the container side to avoid passing base64 via CLI args.
_CONTAINER_SCREENSHOT_PATH = "/home/computron/.desktop_screenshot.png"


async def _run_grounding(task: str) -> dict:
    """Send a grounding request to the in-container grounding server.

    Reads the screenshot from the shared volume file that
    capture_screenshot() already wrote — avoids passing large base64
    strings as CLI arguments.
    """
    cfg = load_config()
    container_name = cfg.virtual_computer.container_name
    container_user = cfg.virtual_computer.container_user

    # The script reads the screenshot from disk inside the container,
    # base64-encodes it, and sends it to the grounding server.
    script = (
        "import sys; sys.path.insert(0, '/opt/inference'); "
        "import base64, json; "
        "from grounding_client import ground; "
        "img = base64.b64encode(open(%s, 'rb').read()).decode(); "
        "result = ground(img, %s); "
        "print(json.dumps(result), flush=True)"
        % (repr(_CONTAINER_SCREENSHOT_PATH), repr(task))
    )

    loop = asyncio.get_running_loop()

    def _exec_sync() -> str:
        import subprocess

        result = subprocess.run(
            [
                "podman", "exec", "-u", container_user,
                container_name,
                "python3", "-c", script,
            ],
            capture_output=True,
            timeout=_REQUEST_TIMEOUT,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            msg = "Grounding failed: %s" % stderr
            raise RuntimeError(msg)
        return result.stdout.decode("utf-8", errors="replace").strip()

    raw = await loop.run_in_executor(None, _exec_sync)

    # Parse the last line of output (skip any loading messages)
    for line in reversed(raw.split("\n")):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)

    msg = "Grounding server returned no JSON: %s" % raw[:200]
    raise RuntimeError(msg)
