"""Tool for reading a file and sending it to the UI."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from config import load_config
from sdk.events import AgentEvent, FileOutputPayload, publish_event

logger = logging.getLogger(__name__)


async def send_file(path: str) -> dict[str, str]:
    """Send a file to the user. Use this whenever the user should receive a file.

    The file MUST live under the virtual computer's home directory
    (``/home/computron`` by default) — only paths under that directory are
    served to the UI. Files in ``/tmp`` or other locations cannot be sent;
    write or copy them into the home directory first.

    Args:
        path: Absolute path to the file, under the home directory.

    Returns:
        Dict with ``status`` and ``message``.
    """
    file_path = Path(path)

    try:
        if not file_path.exists():
            return {"status": "error", "message": "File not found: %s" % path}

        if not file_path.is_file():
            return {"status": "error", "message": "Path is not a file: %s" % path}

        cfg = load_config()
        home_dir = Path(cfg.virtual_computer.home_dir).resolve()
        resolved = file_path.resolve()
        if not resolved.is_relative_to(home_dir):
            return {
                "status": "error",
                "message": (
                    "File must live under %s to be sent to the UI; got %s. "
                    "Write or copy the file into the home directory first."
                    % (home_dir, path)
                ),
            }

        content_type, _ = mimetypes.guess_type(file_path.name)
        if content_type is None:
            content_type = "application/octet-stream"

        filename = file_path.name
        file_size = file_path.stat().st_size

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
            "message": "File '%s' (%d bytes, %s) sent to the UI." % (filename, file_size, content_type),
        }
    except PermissionError:
        return {"status": "error", "message": "Permission denied: %s" % path}
    except OSError as exc:
        logger.exception("Failed to send file %s", path)
        return {"status": "error", "message": "Failed to read file: %s" % exc}
