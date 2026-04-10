"""Shared grounding client for UI-TARS inference.

Writes a screenshot to a temp directory, invokes the grounding server
locally, and returns an action prediction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# First launch may need to download model weights (~31 GB) + load into VRAM.
# Subsequent calls are fast (~5 s inference).
_REQUEST_TIMEOUT = 1860.0  # 31 minutes — covers first-time download + startup

# Subdirectory on the shared volume used for screenshot transfer.
_VISION_DIR = ".vision"


@dataclass(frozen=True, slots=True)
class GroundingResponse:
    """Parsed response from the UI-TARS grounding server."""

    x: int | None = field(default=None)
    """Screen-space pixel x coordinate (None for non-coordinate actions)."""

    y: int | None = field(default=None)
    """Screen-space pixel y coordinate (None for non-coordinate actions)."""

    thought: str = ""
    """Model reasoning (for logging / debug)."""

    action_type: str = "unknown"
    """Detected action kind — ``"click"``, ``"type"``, etc."""

    raw: dict = field(default_factory=dict)
    """Full server response for downstream consumers that need extra fields."""


async def run_grounding(
    screenshot_bytes: bytes,
    task: str,
    *,
    screenshot_filename: str | None = None,
) -> GroundingResponse:
    """Send a screenshot to the UI-TARS grounding server and return an action.

    Args:
        screenshot_bytes: Raw PNG bytes of the screenshot.
        task: Natural-language description of the action to perform.
        screenshot_filename: Filename within the .vision/ folder on the shared
            volume (distinct per caller to avoid concurrent-write races).

    Returns:
        Parsed grounding response with action prediction.

    Raises:
        RuntimeError: If the inference container is unreachable or the
            grounding server fails.
    """
    if screenshot_filename is None:
        from sdk.events import get_current_agent_id
        agent_id = get_current_agent_id() or "default"
        safe_id = agent_id.replace(".", "_")
        screenshot_filename = f"grounding_{safe_id}.png"

    # Write screenshot to a temp .vision/ directory.
    vision_dir = Path("/tmp") / _VISION_DIR
    vision_dir.mkdir(exist_ok=True)
    screenshot_path = vision_dir / screenshot_filename
    screenshot_path.write_bytes(screenshot_bytes)

    script = (
        "import sys; sys.path.insert(0, '/opt/computron/container'); "
        "import json; "
        "from grounding_client import ground_from_path; "
        "result = ground_from_path(%s, %s); "
        "print(json.dumps(result), flush=True)"
        % (repr(str(screenshot_path)), repr(task))
    )

    loop = asyncio.get_running_loop()
    raw_output = await loop.run_in_executor(None, _exec_grounding, script)

    return _parse_response(raw_output)


def _exec_grounding(script: str) -> str:
    """Run the grounding script locally."""
    result = subprocess.run(
        ["python3", "-c", script],
        capture_output=True,
        timeout=_REQUEST_TIMEOUT,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        msg = "Grounding failed: %s" % stderr
        raise RuntimeError(msg)
    return result.stdout.decode("utf-8", errors="replace").strip()


def _parse_response(raw_output: str) -> GroundingResponse:
    """Extract the JSON response and build a ``GroundingResponse``."""
    # The grounding server prints JSON on the last line; earlier lines may
    # contain model-loading log messages.
    data: dict | None = None
    for line in reversed(raw_output.split("\n")):
        line = line.strip()
        if line.startswith("{"):
            data = json.loads(line)
            break

    if data is None:
        msg = "Grounding server returned no JSON: %s" % raw_output[:200]
        raise RuntimeError(msg)

    # Extract coordinates when present (click, scroll, drag, etc.).
    # Actions like type, hotkey, wait, finished have no coordinates.
    x: int | None = None
    y: int | None = None
    coords = data.get("coordinates")
    if coords:
        x = int(data.get("x", coords[0]["screen"][0]))
        y = int(data.get("y", coords[0]["screen"][1]))

    return GroundingResponse(
        x=x,
        y=y,
        thought=data.get("thought", ""),
        action_type=data.get("action_type", "unknown"),
        raw=data,
    )
