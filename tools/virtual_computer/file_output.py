"""Tool for reading a file from the virtual computer and sending it to the UI."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from sdk.events import AgentEvent, FileOutputPayload, publish_event
from config import load_config

logger = logging.getLogger(__name__)


async def output_file(path: str) -> dict[str, str]:
    """Deliver a file to the user as a downloadable card.

    Args:
        path: Absolute path inside the container (e.g. ``/home/computron/report.csv``).

    Returns:
        Dict with ``status`` and ``message``.
    """
    cfg = load_config()
    container_home = cfg.virtual_computer.container_working_dir.rstrip("/") + "/"
    host_home = cfg.virtual_computer.home_dir

    if not path.startswith(container_home):
        return {
            "status": "error",
            "message": f"Path must be inside {container_home}. Got: {path}",
        }

    relative = path[len(container_home) :]
    host_path = Path(host_home) / relative

    if not host_path.exists():
        return {"status": "error", "message": f"File not found: {path}"}

    if not host_path.is_file():
        return {"status": "error", "message": f"Path is not a file: {path}"}

    content_type, _ = mimetypes.guess_type(host_path.name)
    if content_type is None:
        content_type = "application/octet-stream"

    filename = host_path.name
    file_size = host_path.stat().st_size

    payload = FileOutputPayload(
        type="file_output",
        filename=filename,
        content_type=content_type,
        path=path,
    )
    publish_event(AgentEvent(payload=payload))
    logger.info("Emitted file_output event for %s (%s, %d bytes)", filename, content_type, file_size)

    return {
        "status": "ok",
        "message": f"File '{filename}' ({file_size} bytes, {content_type}) sent to the UI.",
    }
