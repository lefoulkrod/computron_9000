"""Tool for playing an audio file directly in the browser."""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

from sdk.events import AgentEvent, AudioPlaybackPayload, publish_event

logger = logging.getLogger(__name__)


async def play_audio(path: str) -> dict[str, str]:
    """Play an audio file in the browser.

    Args:
        path: Absolute path to the audio file.

    Returns:
        Dict with ``status`` and ``message``.
    """
    file_path = Path(path)

    try:
        if not file_path.exists():
            return {"status": "error", "message": "File not found: %s" % path}

        if not file_path.is_file():
            return {"status": "error", "message": "Path is not a file: %s" % path}

        raw = file_path.read_bytes()

        content_type, _ = mimetypes.guess_type(file_path.name)
        if content_type is None or not content_type.startswith("audio/"):
            content_type = "audio/mpeg"

        encoded = base64.b64encode(raw).decode("ascii")

        payload = AudioPlaybackPayload(
            type="audio_playback",
            content_type=content_type,
            content=encoded,
        )
        publish_event(AgentEvent(payload=payload))
        logger.info("Emitted audio_playback event for %s (%s, %d bytes)", file_path.name, content_type, len(raw))

        return {"status": "ok", "message": "Playing '%s' (%d bytes)." % (file_path.name, len(raw))}
    except PermissionError:
        return {"status": "error", "message": "Permission denied: %s" % path}
    except OSError as exc:
        logger.exception("Failed to read audio file %s", path)
        return {"status": "error", "message": "Failed to read file: %s" % exc}
