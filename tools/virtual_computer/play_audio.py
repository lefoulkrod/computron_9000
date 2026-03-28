"""Tool for playing an audio file directly in the browser."""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

from sdk.events import AgentEvent, AudioPlaybackPayload, publish_event
from config import load_config

logger = logging.getLogger(__name__)


async def play_audio(path: str) -> dict[str, str]:
    """Play an audio file in the browser.

    Supports WAV, MP3, OGG, FLAC, etc. Generate the audio file first
    inside the container, then pass its path here.

    Args:
        path: Absolute path inside the container (e.g. ``/home/computron/speech.wav``).

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

    try:
        raw = host_path.read_bytes()
    except OSError as exc:
        logger.exception("Failed to read audio file %s", host_path)
        return {"status": "error", "message": f"Failed to read file: {exc}"}

    content_type, _ = mimetypes.guess_type(host_path.name)
    if content_type is None or not content_type.startswith("audio/"):
        content_type = "audio/mpeg"

    encoded = base64.b64encode(raw).decode("ascii")

    payload = AudioPlaybackPayload(
        type="audio_playback",
        content_type=content_type,
        content=encoded,
    )
    publish_event(AgentEvent(event=payload))
    logger.info("Emitted audio_playback event for %s (%s, %d bytes)", host_path.name, content_type, len(raw))

    return {"status": "ok", "message": f"Playing '{host_path.name}' ({len(raw)} bytes)."}
