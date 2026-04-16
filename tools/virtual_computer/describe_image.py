"""Tool for analyzing images using the vision model."""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path
from typing import cast

from ollama import AsyncClient, Image

from config import load_config

logger = logging.getLogger(__name__)

_SUPPORTED_IMAGE_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }
)


async def describe_image(
    path: str,
    prompt: str = "Describe this image concisely. List key visual elements and any readable text.",
) -> str:
    """Analyze an image file using the vision model.

    Args:
        path: Absolute path to the image file
        prompt: Question or instruction about the image.

    Returns:
        The vision model's textual response.
    """
    t0 = asyncio.get_event_loop().time()

    cfg = load_config()
    file_path = Path(path)

    if not file_path.exists():
        return "Error: File not found: %s" % path

    if not file_path.is_file():
        return "Error: Path is not a file: %s" % path

    content_type, _ = mimetypes.guess_type(file_path.name)
    if content_type not in _SUPPORTED_IMAGE_TYPES:
        return "Error: Unsupported image type '%s' for %s. Supported: %s" % (
            content_type,
            file_path.name,
            ", ".join(sorted(_SUPPORTED_IMAGE_TYPES)),
        )

    try:
        raw = file_path.read_bytes()
    except PermissionError:
        return "Error: Permission denied: %s" % path
    except OSError as exc:
        logger.exception("Failed to read image file %s", path)
        return "Error: Failed to read file: %s" % exc

    encoded = base64.b64encode(raw).decode("ascii")

    from settings import load_settings
    vision_model = load_settings().get("vision_model")
    if not vision_model:
        return "Error: No vision model configured. Set one in Settings > System."

    host = cfg.llm.host if getattr(cfg, "llm", None) else None
    client = AsyncClient(host=host) if host else AsyncClient()

    try:
        response = await client.generate(
            model=vision_model,
            prompt=prompt,
            images=[Image(value=encoded)],
        )
    except Exception as exc:
        logger.exception("Vision model failed for image %s", path)
        return "Error: Vision model failed: %s" % exc

    answer = cast(str | None, getattr(response, "response", None))
    if answer is None:
        return "Error: Vision model did not return a response."

    from tools._vision_logging import log_vision_panel

    elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
    log_vision_panel(
        "describe_image",
        vision_model,
        prompt,
        answer,
        elapsed_ms,
        image_source=path,
    )

    return answer
