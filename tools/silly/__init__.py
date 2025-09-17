"""Playful / whimsical tools.

Public API:
- generate_emoticon: Return a random playful ASCII/unicode emoticon.
"""

from .generate_emoticon import (
    EmoticonGenerationError,
    EmoticonResult,
    generate_emoticon,
)

__all__ = [
    "EmoticonGenerationError",
    "EmoticonResult",
    "generate_emoticon",
]
