"""Streaming music generation tool with real-time progress updates.

Runs generation inside the container via the persistent inference server's
``/generate-stream`` endpoint, reads chunked JSONL output, and publishes
``GenerationPreviewPayload`` events so the frontend can display live
progress updates.

Uses ACE-Step 1.5 for full song generation — a two-stage model with an LM
planner and DiT executor, capable of generating high-quality music with vocals.
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
logger = logging.getLogger(__name__)

_STREAM_TIMEOUT: float = 900.0  # 15 minutes max for generation


# ACE-Step 1.5 quality presets — controls inference steps and LM planning.
_QUALITY_PRESETS = {
    "fast":    {"steps": 4,  "thinking": False},
    "quality": {"steps": 8,  "thinking": True},
    "best":    {"steps": 16, "thinking": True},
}

# Style presets — optimized DiT and LM parameters for different music scenarios.
# Based on ACE-Step 1.5 community research and official tuning guide.
# Maps to GenerationParams fields: guidance_scale, shift, lm_temperature, etc.
_STYLE_PRESETS: dict[str, dict] = {
    "pop": {
        "guidance_scale": 5.0, "shift": 4.0,
        "lm_temperature": 0.85, "lm_cfg_scale": 2.5,
    },
    "rock": {
        "guidance_scale": 5.0, "shift": 5.0,
        "lm_temperature": 0.85, "lm_cfg_scale": 2.5,
    },
    "hiphop": {
        "guidance_scale": 3.5, "shift": 3.5,
        "lm_temperature": 0.85, "lm_cfg_scale": 2.0,
    },
    "electronic": {
        "guidance_scale": 5.0, "shift": 4.0,
        "lm_temperature": 0.85, "lm_cfg_scale": 2.0,
    },
    "jazz": {
        "guidance_scale": 2.5, "shift": 3.0,
        "lm_temperature": 0.75, "lm_cfg_scale": 2.0,
    },
    "classical": {
        "guidance_scale": 2.0, "shift": 3.0,
        "lm_temperature": 0.70, "lm_cfg_scale": 2.0,
    },
    "ambient": {
        "guidance_scale": 1.5, "shift": 2.5,
        "lm_temperature": 0.80, "lm_cfg_scale": 2.0,
    },
    "metal": {
        "guidance_scale": 1.5, "shift": 4.0,
        "lm_temperature": 0.85, "lm_cfg_scale": 2.0,
    },
    "lofi": {
        "guidance_scale": 1.5, "shift": 2.5,
        "lm_temperature": 0.80, "lm_cfg_scale": 2.0,
    },
}


async def generate_music(
    prompt: str,
    lyrics: str = "",
    duration: float = 60.0,
    quality: str = "quality",
    style: str = "",
) -> dict[str, str]:
    """Generate music using ACE-Step 1.5.

    ACE-Step 1.5 is a two-stage model (LM planner + DiT diffusion) that
    generates full songs with vocals up to 10 minutes long.

    Args:
        prompt: Describe genre, mood, vocal style, instruments, tempo, key,
            and production style. Be specific — detailed prompts produce
            much better results. Format::

                [Genre], [Vocal type], [Emotion], [Instruments], [Tempo], [Key]

            Examples:
                "pop-rock, powerful female vocal, energetic, driving drums
                 and synth bass, 128 bpm, E major, anthemic chorus"
                "ambient lo-fi hip-hop, warm Rhodes piano with vinyl crackle,
                 boom-bap drums, 75 bpm, D minor, bedroom production"

        lyrics: Song lyrics with structure tags. Leave empty for instrumental.
            Use tags like [verse], [chorus], [bridge], [intro], [outro],
            [interlude], [hook], [break], [pre-chorus], [post-chorus].
            Add style hints to tags for vocal control::

                [verse - whispered]
                Walking down the empty street
                The city lights shine at my feet

                [chorus - powerful]
                We're alive tonight
                Nothing's gonna stop us now

                [outro - fade out]

            For instrumental, use "[Instrumental]" or structure tags with
            instrument hints like "[Intro - ambient pads]", "[Theme A - piano]".
            Supports 17 languages including English, Spanish, Chinese,
            Japanese, French, German, Korean, and more.

        duration: Length in seconds (max 600s / 10 min). Sweet spots:
            - 30-60s for previews / fast iteration
            - 90-120s for vocal tracks (best quality range)
            - 60-90s for instrumental (shorter = more coherent)

        quality: Controls inference steps and LM planning:
            - "fast": 4 steps, no LM — instant previews
            - "quality": 8 steps with LM planning (default, good balance)
            - "best": 16 steps with LM planning (highest fidelity)

        style: Genre preset that auto-tunes internal parameters for optimal
            results. Pick the closest match to the requested genre:
            - "pop": bright, catchy, strong vocal presence
            - "rock": driving energy, anthemic structure
            - "hiphop": rhythmic, punchy beats, flow-focused
            - "electronic": synth-heavy, EDM, dance, techno
            - "jazz": warm, natural, acoustic instruments
            - "classical": orchestral, precise, composed
            - "ambient": textural, atmospheric, spacious
            - "metal": heavy, aggressive, intense
            - "lofi": warm, vintage, relaxed
            Leave empty to use default parameters (works well for most cases).

    Returns:
        Dict with ``status``, ``path``, and ``media_type``.
    """
    media_type = "audio"
    gen_id = uuid.uuid4().hex[:12]

    # Resolve quality preset
    preset = _QUALITY_PRESETS.get(quality, _QUALITY_PRESETS["quality"])

    # Construct parameters dict for the inference client
    params: dict = {
        "lyrics": lyrics,
        "duration": min(duration, 600.0),  # Cap at 10 minutes (v1.5 max)
        "steps": preset["steps"],
        "thinking": preset["thinking"],
    }

    # Apply style preset (tuned guidance_scale, shift, lm params)
    style_preset = _STYLE_PRESETS.get(style.lower(), {}) if style else {}
    params.update(style_preset)

    params_repr = repr(params)

    script = (
        "import sys; sys.path.insert(0, '/opt/computron/container'); "
        "import json; "
        "from inference_client import generate_stream; "
        "[print(json.dumps(e), flush=True) for e in generate_stream('audio', %r, **%s)]"
        % (prompt, params_repr)
    )

    # Publish initial loading event
    _publish_preview(gen_id, media_type, status="loading", message="Starting music generation with ACE-Step...")

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024,
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

        # The inference server writes directly to /home/computron/.
        host_path = Path(final_path)
        ui_path = final_path

        if host_path.exists() and host_path.is_file():
            content_type = mimetypes.guess_type(host_path.name)[0] or "audio/wav"

            # Publish final preview with the virtual computer path
            _publish_preview(
                gen_id, media_type,
                status="complete",
                output_path=ui_path,
                output_content_type=content_type,
                message="Generation complete",
            )

            # Also emit a FileOutputPayload for the chat message
            publish_event(AgentEvent(payload=FileOutputPayload(
                type="file_output",
                filename=host_path.name,
                content_type=content_type,
                path=ui_path,
            )))
            logger.info("Music generation complete: %s (%s)", host_path.name, content_type)
        else:
            _publish_preview(gen_id, media_type, status="complete",
                             message="Generation complete (file not accessible on host)")
            logger.warning("Generated file not found on host: %s", host_path)

        return {"status": "ok", "path": ui_path, "media_type": media_type}

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
