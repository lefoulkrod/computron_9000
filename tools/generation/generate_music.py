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


async def generate_music(
    prompt: str,
    negative_prompt: str = "",
    duration: float = 30.0,
    steps: int = 27,
    cfg_scale: float = 7.0,
    seed: int = -1,
) -> dict[str, str]:
    """Generate music using ACE-Step.

    ACE-Step is a diffusion-based music generation model capable of creating
    full songs up to 4 minutes in length. It uses natural language prompts
    to generate high-quality instrumental music.

    Args:
        prompt: Text describing the music (genre, mood, instruments, etc.).
        negative_prompt: Things to avoid in the generated music.
        duration: Length of the generated audio in seconds (max 240s / 4 min).
        steps: Inference steps (higher = better quality, default 27).
        cfg_scale: CFG guidance scale (default 7.0).
        seed: Random seed (-1 for random).

    Returns:
        Dict with ``status``, ``path``, and ``media_type``.
    """
    media_type = "audio"
    gen_id = uuid.uuid4().hex[:12]
    cfg = load_config()
    container_name = cfg.inference_container.container_name
    container_user = cfg.inference_container.container_user

    # Construct parameters dict for the inference client
    params = {
        "negative_prompt": negative_prompt,
        "duration": min(duration, 240.0),  # Cap at 4 minutes
        "steps": steps,
        "cfg_scale": cfg_scale,
        "seed": seed if seed >= 0 else None,
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
            content_type = "audio/wav"

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
