"""Tool that returns a random playful ASCII emoticon.

Intended for occasional light-hearted responses to add personality.
"""

from __future__ import annotations

import logging
import secrets
from typing import ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EmoticonGenerationError(RuntimeError):
    """Raised when the emoticon tool fails unexpectedly."""


class EmoticonResult(BaseModel):
    """Result model for the generate_emoticon tool.

    Attributes:
        status: "success" or "error".
        emoticon: The randomly selected emoticon when successful.
        choices: The pool of possible emoticons (returned for transparency / prompting context).
        error_message: Populated when status == "error".
    """

    status: str
    emoticon: str | None = None
    choices: list[str] | None = None
    error_message: str | None = None

    # Public registry of valid emoticons (kept small and curated)
    EMOTICONS: ClassVar[list[str]] = [
        "(~v\\¬)",
        "(>‿<)",
        "(¬‿¬)",
        "(ʘ‿ʘ)",
        "(づ｡◕‿‿◕｡)づ",
        "(☞ﾟヮﾟ)☞",
        "(☞⌐■_■)☞",
        "(ʕ•ᴥ•ʔ)",
        "(ᵔᴥᵔ)",
        "(╯°□°)╯︵ ┻━┻",
        "┬─┬ ノ( ゜-゜ノ)",
        "¯\\_(ツ)_/¯",
    ]


def generate_emoticon() -> EmoticonResult:
    """Return a random playful ASCII emoticon.

    Returns:
        EmoticonResult: Pydantic model with status, emoticon, and available choices.
    """
    try:
        choices = EmoticonResult.EMOTICONS
        if not choices:
            msg = "No emoticons available"
            raise EmoticonGenerationError(msg)
        emoticon = secrets.choice(choices)
        logger.info("Selected emoticon %s", emoticon)
        return EmoticonResult(status="success", emoticon=emoticon, choices=choices)
    except Exception as exc:  # broad to ensure tool never crashes caller
        # Let logging.formatException capture details without duplicating message text
        logger.exception("Failed to generate emoticon")
        return EmoticonResult(
            status="error",
            error_message=str(exc),
            choices=EmoticonResult.EMOTICONS,
        )


__all__ = [
    "EmoticonGenerationError",
    "EmoticonResult",
    "generate_emoticon",
]
