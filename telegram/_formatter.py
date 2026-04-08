"""Format agent output for Telegram delivery."""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["TelegramFormatter"]

# Telegram message size limit.
_MSG_LIMIT = 4096


class TelegramFormatter:
    """Prepares agent text for Telegram: splitting, escaping, truncating."""

    # -- public API -----------------------------------------------------

    @staticmethod
    def split(text: str, *, limit: int = _MSG_LIMIT) -> list[str]:
        """Split *text* into chunks that fit Telegram's message size limit.

        Prefers paragraph boundaries, then sentence boundaries, then
        falls back to hard splitting at *limit*.
        """
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            # Try paragraph break
            cut = remaining.rfind("\n\n", 0, limit)
            if cut == -1:
                # Try single newline
                cut = remaining.rfind("\n", 0, limit)
            if cut == -1:
                # Try sentence boundary
                cut = max(
                    remaining.rfind(". ", 0, limit),
                    remaining.rfind("! ", 0, limit),
                    remaining.rfind("? ", 0, limit),
                )
            if cut == -1 or cut < limit // 4:
                # Hard split
                cut = limit

            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip("\n")

        return chunks

    @staticmethod
    def escape_markdown(text: str) -> str:
        """Escape characters that are special in Telegram MarkdownV2."""
        special = r"_*[]()~`>#+-=|{}.!"
        return re.sub(r"([%s])" % re.escape(special), r"\\\1", text)

    @staticmethod
    def file_caption(path: Path, *, index: int = 0, total: int = 1) -> str:
        """Build a short caption for an attached file."""
        name = path.name
        if total == 1:
            return f"📎 {name}"
        return f"📎 {name} ({index + 1}/{total})"