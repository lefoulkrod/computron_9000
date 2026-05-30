"""Format agent output for Telegram delivery."""

from __future__ import annotations

from pathlib import Path

import telegramify_markdown

__all__ = ["TelegramFormatter"]

# Telegram's per-message limit, in UTF-16 code units.
_TELEGRAM_MSG_LIMIT = 4096


class TelegramFormatter:
    """Prepares agent text for Telegram.

    The agent emits CommonMark-flavored markdown (``**bold**``, fenced
    code, lists, links). Telegram's MarkdownV2 uses different syntax and
    requires escaping of many punctuation characters. We delegate the
    conversion and the chunk splitting to ``telegramify_markdown`` so the
    result renders natively in the Telegram client instead of showing
    literal asterisks and backticks.
    """

    @staticmethod
    def to_markdownv2_chunks(text: str) -> list[str]:
        """Convert ``text`` to MarkdownV2 and split to fit Telegram's limit.

        Each returned chunk must be sent with ``parse_mode="MarkdownV2"``.

        ``convert`` produces a plain text + entities pair.
        ``split_markdownv2`` budgets against the **rendered** MarkdownV2
        size so chunks that grow under escaping (``.`` → ``\\.``) still
        fit Telegram's 4096-code-unit limit, and won't cut a formatting
        span in half.
        """
        plain_text, entities = telegramify_markdown.convert(text)
        return telegramify_markdown.split_markdownv2(
            plain_text, entities, _TELEGRAM_MSG_LIMIT,
        )

    @staticmethod
    def file_caption(path: Path, *, index: int = 0, total: int = 1) -> str:
        """Build a short caption for an attached file."""
        name = path.name
        if total == 1:
            return f"📎 {name}"
        return f"📎 {name} ({index + 1}/{total})"
