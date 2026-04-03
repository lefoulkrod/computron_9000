"""Streaming music generation tool with real-time progress updates.

Runs generation inside the container via the persistent inference server's
``/generate-stream`` endpoint, reads chunked JSONL output, and publishes
``GenerationPreviewPayload`` events so the frontend can display live
progress updates.

Uses ACE-Step (ACE-Step-v1-3.5B) for full song generation - a diffusion-based
model capable of generating high-quality music up to 4 minutes in length.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import uuid
from pathlib import Path

from sdk.events import (
    AgentEvent,
    FileOutputPayload,
    GenerationPreviewPayload,
    publish_event,
)
from config import load_config

logger = logging.getLogger(__name__)

_STREAM_TIMEOUT: float = 900.0  # 15 minutes max for generation


_QUALITY_PRESETS = {
    "fast": {
        "instrumental": {"steps": 25, "scheduler_type": "pingpong", "cfg_scale": 15.0,
                         "guidance_interval": 0.5, "omega_scale": 10},
        "vocal":        {"steps": 25, "scheduler_type": "pingpong", "cfg_scale": 15.0,
                         "guidance_interval": 0.7, "omega_scale": 15},
    },
    "quality": {
        "instrumental": {"steps": 60, "scheduler_type": "euler", "cfg_scale": 15.0,
                         "guidance_interval": 0.5, "omega_scale": 10},
        "vocal":        {"steps": 60, "scheduler_type": "euler", "cfg_scale": 15.0,
                         "guidance_interval": 0.7, "omega_scale": 15},
    },
    "best": {
        "instrumental": {"steps": 80, "scheduler_type": "euler", "cfg_scale": 15.0,
                         "guidance_interval": 0.6, "omega_scale": 15},
        "vocal":        {"steps": 80, "scheduler_type": "euler", "cfg_scale": 15.0,
                         "guidance_interval": 0.8, "omega_scale": 25},
    },
}


async def generate_music(
    prompt: str,
    lyrics: str = "",
    duration: float = 60.0,
    quality: str = "quality",
) -> dict[str, str]:
    """Generate music using ACE-Step.

    ACE-Step is a diffusion-based music generation model capable of creating
    full songs with vocals up to 4 minutes in length.

    Args:
        prompt: Text describing the music style (genre, mood, instruments).
            Example: "Upbeat pop song with synths and guitar"
        lyrics: Song lyrics with structure tags. Use [verse], [chorus],
            [bridge], [intro], [outro], [interlude], [hook], [break],
            [pre-chorus], [post-chorus] to define sections. Leave empty
            for instrumental music. Example::

                [verse]
                Walking down the empty street
                The city lights shine at my feet

                [chorus]
                We're alive tonight
                Nothing's gonna stop us now

            Supports 17 languages including English, Spanish, Chinese,
            Japanese, French, German, Korean, and more.
        duration: Length of the generated audio in seconds (max 240s / 4 min).
        quality: "fast" (quick drafts), "quality" (default, good balance),
            or "best" (highest quality, slower).

    Returns:
        Dict with ``status``, ``path``, and ``media_type``.
    """
    media_type = "audio"
    gen_id = uuid.uuid4().hex[:12]
    cfg = load_config()
    container_name = cfg.inference_container.container_name
    container_user = cfg.inference_container.container_user

    # Resolve quality preset, auto-selecting vocal vs instrumental settings
    quality_tier = _QUALITY_PRESETS.get(quality, _QUALITY_PRESETS["quality"])
    preset = quality_tier["vocal"] if lyrics else quality_tier["instrumental"]

    # Construct parameters dict for the inference client
    params = {
        "lyrics": lyrics,
        "duration": min(duration, 240.0),  # Cap at 4 minutes
        "steps": preset["steps"],
        "cfg_scale": preset["cfg_scale"],
        "scheduler_type": preset["scheduler_type"],
        "guidance_interval": preset["guidance_interval"],
        "omega_scale": preset["omega_scale"],
    }
    params_json = json.dumps(params)

    # Construct a compact script to run inside the container
    script = (
        "import sys; sys.path.insert(0, '/opt/inference'); "
        "import json; "
        "from inference_client import generate_stream; "
        f"[print(json.dumps(e), flush=True) for e in generate_stream('audio', {prompt!r}, **{params_json})]"
    )

    # Publish initial loading event
    _publish_preview(gen_id, media_type, status="loading", message="Starting music generation with ACE-Step...")

    try:
        # Use a large buffer limit for any preview data
        proc = await asyncio.create_subprocess_exec(
            "podman", "exec", "-u", container_user, container_name,
            "python3", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024,  # 1MB line buffer
        )

        final_path: str | None = None
        fail_message: str | None = None

        async def _read_stream() -> None:
            nonlocal final_path, fail_message
            assert proc.stdout is not None
            while True:
                raw_line = await proc.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON line: %s", line[:100])
                    continue

                status = event.get("status", "generating")

                if status == "complete":
                    final_path = event.get("path")
                    _publish_preview(gen_id, media_type, status="generating",
                                     step=event.get("step"), total_steps=event.get("total_steps"),
                                     message="Finalizing...")
                elif status == "failed":
                    fail_message = event.get("message", "Generation failed")
                    _publish_preview(gen_id, media_type, status="failed",
                                     message=fail_message)
                else:
                    _publish_preview(
                        gen_id, media_type,
                        status=status,
                        step=event.get("step"),
                        total_steps=event.get("total_steps"),
                        preview=event.get("preview"),
                        message=event.get("message"),
                    )

        await asyncio.wait_for(_read_stream(), timeout=_STREAM_TIMEOUT)
        await proc.wait()

        if fail_message is not None:
            return {"status": "error", "message": fail_message}

        if proc.returncode != 0 and final_path is None:
            stderr_data = await proc.stderr.read() if proc.stderr else b""
            err_msg = stderr_data.decode("utf-8", errors="replace").strip()
            _publish_preview(gen_id, media_type, status="failed",
                             message=err_msg or "Generation process failed")
            return {"status": "error", "message": err_msg or "Generation process failed"}

        if final_path is None:
            _publish_preview(gen_id, media_type, status="failed",
                             message="No output path received from generator")
            return {"status": "error", "message": "No output path received"}

        # Read the generated file from the host volume and emit the final preview
        container_home = cfg.inference_container.container_working_dir.rstrip("/") + "/"
        host_home = cfg.inference_container.home_dir

        if final_path.startswith(container_home):
            relative = final_path[len(container_home):]
            host_path = Path(host_home) / relative
        else:
            host_path = Path(host_home) / final_path.lstrip("/")

        if host_path.exists() and host_path.is_file():
            content_type = mimetypes.guess_type(host_path.name)[0] or "audio/wav"

            # Publish final preview referencing the container path
            _publish_preview(
                gen_id, media_type,
                status="complete",
                output_path=final_path,
                output_content_type=content_type,
                message="Generation complete",
            )

            # Also emit a FileOutputPayload for the chat message
            publish_event(AgentEvent(payload=FileOutputPayload(
                type="file_output",
                filename=host_path.name,
                content_type=content_type,
                path=final_path,
            )))
            logger.info("Music generation complete: %s (%s)", host_path.name, content_type)
        else:
            _publish_preview(gen_id, media_type, status="complete",
                             message="Generation complete (file not accessible on host)")
            logger.warning("Generated file not found on host: %s", host_path)

        return {"status": "ok", "path": final_path, "media_type": media_type}

    except TimeoutError:
        proc.kill()
        _publish_preview(gen_id, media_type, status="failed",
                         message=f"Generation timed out after {_STREAM_TIMEOUT}s")
        return {"status": "error", "message": "Generation timed out"}
    except Exception as exc:
        logger.exception("generate_music failed")
        _publish_preview(gen_id, media_type, status="failed", message=str(exc))
        return {"status": "error", "message": str(exc)}


def _publish_preview(
    gen_id: str,
    media_type: str,
    *,
    status: str = "generating",
    step: int | None = None,
    total_steps: int | None = None,
    preview: str | None = None,
    message: str | None = None,
    output: str | None = None,
    output_content_type: str | None = None,
    output_path: str | None = None,
) -> None:
    """Publish a GenerationPreviewPayload event."""
    publish_event(AgentEvent(payload=GenerationPreviewPayload(
        type="generation_preview",
        gen_id=gen_id,
        media_type=media_type,
        status=status,  # type: ignore[arg-type]
        step=step,
        total_steps=total_steps,
        preview=preview,
        message=message,
        output=output,
        output_content_type=output_content_type,
        output_path=output_path,
    )))
