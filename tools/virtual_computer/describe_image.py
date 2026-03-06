"""Tool for analyzing images from the virtual computer using the vision model."""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import cast

from ollama import AsyncClient, Image

from config import load_config
from models.model_configs import get_model_by_name

logger = logging.getLogger(__name__)

_SUPPORTED_IMAGE_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
})


async def describe_image(
    path: str,
    prompt: str = "Describe this image in detail.",
) -> str:
    """Analyze an image file from the virtual computer using the vision model.

    Args:
        path: Absolute path inside the container
            (e.g. ``/home/computron/uploads/photo.jpg``).
        prompt: Question or instruction about the image.

    Returns:
        The vision model's textual response.
    """
    cfg = load_config()
    container_home = cfg.virtual_computer.container_working_dir.rstrip("/") + "/"
    host_home = cfg.virtual_computer.home_dir

    if not path.startswith(container_home):
        return f"Error: Path must be inside {container_home}. Got: {path}"

    relative = path[len(container_home):]
    host_path = Path(host_home) / relative

    if not host_path.exists():
        return f"Error: File not found: {path}"

    if not host_path.is_file():
        return f"Error: Path is not a file: {path}"

    content_type, _ = mimetypes.guess_type(host_path.name)
    if content_type not in _SUPPORTED_IMAGE_TYPES:
        return (
            f"Error: Unsupported image type '{content_type}' for {host_path.name}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_IMAGE_TYPES))}"
        )

    try:
        raw = host_path.read_bytes()
    except OSError as exc:
        logger.exception("Failed to read image file %s", host_path)
        return f"Error: Failed to read file: {exc}"

    encoded = base64.b64encode(raw).decode("ascii")

    model = get_model_by_name("vision")
    host = cfg.llm.host if getattr(cfg, "llm", None) else None
    client = AsyncClient(host=host) if host else AsyncClient()

    try:
        response = await client.generate(
            model=model.model,
            prompt=prompt,
            options=model.options,
            images=[Image(value=encoded)],
            think=model.think,
        )
    except Exception as exc:
        logger.exception("Vision model failed for image %s", path)
        return f"Error: Vision model failed: {exc}"

    answer = cast(str | None, getattr(response, "response", None))
    if answer is None:
        return "Error: Vision model did not return a response."

    return answer
