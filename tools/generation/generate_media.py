"""Streaming image generation tool with real-time previews.

Runs generation inside the container via the persistent inference server's
``/generate-stream`` endpoint, reads chunked JSONL output, and publishes
``GenerationPreviewPayload`` events so the frontend can display live
progress and denoising previews.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import uuid
from pathlib import Path

from agents.ollama.sdk.events import AssistantResponse, publish_event
from agents.ollama.sdk.events.models import FileOutputPayload, GenerationPreviewPayload
from config import load_config

logger = logging.getLogger(__name__)

_STREAM_TIMEOUT: float = 900.0  # 15 minutes max for generation


async def generate_media(
    description: str,
    model: str = "schnell",
) -> dict[str, str]:
    """Generate an image with real-time streaming preview.

    Delegates to the container's inference server via ``/generate-stream``.
    Progress and TAESD-decoded preview images are published as
    ``GenerationPreviewPayload`` events in real time.

    Args:
        description: Text prompt describing the image to generate.
        model: Model to use — "schnell" (default, fast), "klein-4b"
            (better quality, Apache 2.0), or "klein-9b" (best quality,
            non-commercial).

    Returns:
        Dict with ``status``, ``path``, and ``media_type``.
    """
    media_type = "image"
    gen_id = uuid.uuid4().hex[:12]
    cfg = load_config()
    container_name = cfg.virtual_computer.container_name
    container_user = cfg.virtual_computer.container_user

    # Construct a compact script to run inside the container
    params_json = json.dumps({"model": model})
    script = (
        "import sys; sys.path.insert(0, '/opt/inference'); "
        "import json; "
        "from inference_client import generate_stream; "
        f"[print(json.dumps(e), flush=True) for e in generate_stream({media_type!r}, {description!r}, **{params_json})]"
    )

    # Publish initial loading event
    _publish_preview(gen_id, media_type, status="loading", message="Starting generation...")

    try:
        # Use a large buffer limit because TAESD preview images in base64
        # can exceed the default 64KB asyncio StreamReader line limit.
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
        container_home = cfg.virtual_computer.container_working_dir.rstrip("/") + "/"
        host_home = cfg.virtual_computer.home_dir

        if final_path.startswith(container_home):
            relative = final_path[len(container_home):]
            host_path = Path(host_home) / relative
        else:
            host_path = Path(host_home) / final_path.lstrip("/")

        if host_path.exists() and host_path.is_file():
            content_type, _ = mimetypes.guess_type(host_path.name)
            if content_type is None:
                content_type = "application/octet-stream"

            # Publish final preview referencing the container path
            _publish_preview(
                gen_id, media_type,
                status="complete",
                output_path=final_path,
                output_content_type=content_type,
                message="Generation complete",
            )

            # Also emit a FileOutputPayload for the chat message
            publish_event(AssistantResponse(event=FileOutputPayload(
                type="file_output",
                filename=host_path.name,
                content_type=content_type,
                path=final_path,
            )))
            logger.info("Generation complete: %s (%s)", host_path.name, content_type)
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
        logger.exception("generate_media failed")
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
    publish_event(AssistantResponse(event=GenerationPreviewPayload(
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
