"""Shared vision helper that routes image prompts through the configured provider."""

import logging
from typing import Any

from settings import load_settings

logger = logging.getLogger(__name__)


async def vision_generate(
    prompt: str,
    image_base64: str,
    *,
    media_type: str = "image/png",
) -> str:
    """Send an image + prompt to the configured vision model via the active provider.

    Reads vision_model, vision_options, and vision_think from settings.json.

    Args:
        prompt: Question or instruction about the image.
        image_base64: Base64-encoded image data.
        media_type: MIME type of the image.

    Returns:
        The model's text response.

    Raises:
        ValueError: If no vision model is configured.
        ProviderError: If the provider call fails.
    """
    settings = load_settings()

    vision_model = settings.get("vision_model")
    if not vision_model:
        msg = "No vision model configured. Set one in Settings > System."
        raise ValueError(msg)

    vision_options: dict[str, Any] = dict(settings.get("vision_options") or {})
    vision_think: bool = bool(settings.get("vision_think") or False)

    from . import get_provider
    provider = get_provider()
    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": prompt,
        "images": [{"data": image_base64, "media_type": media_type}],
    }]

    response = await provider.chat(
        model=vision_model,
        messages=messages,
        options=vision_options,
        think=vision_think,
    )
    return response.message.content or ""
