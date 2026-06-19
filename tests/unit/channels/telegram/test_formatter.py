"""Tests for channels.telegram._formatter.TelegramFormatter."""

from pathlib import Path

import pytest

from channels.telegram._formatter import TelegramFormatter


# ---------------------------------------------------------------------------
# to_markdownv2_chunks() — CommonMark → MarkdownV2 conversion + chunking
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_short_text_returns_single_chunk():
    chunks = TelegramFormatter.to_markdownv2_chunks("hello world")
    assert len(chunks) == 1


@pytest.mark.unit
def test_bold_double_asterisk_converted_to_single_asterisk():
    """Agent emits ``**bold**`` (CommonMark); MarkdownV2 uses ``*bold*``."""
    chunks = TelegramFormatter.to_markdownv2_chunks("hello **world**")
    body = "".join(chunks)
    assert "*world*" in body
    assert "**world**" not in body


@pytest.mark.unit
def test_italic_underscore_in_output():
    """``*italic*`` in CommonMark becomes ``_italic_`` in MarkdownV2."""
    chunks = TelegramFormatter.to_markdownv2_chunks("an *italic* word")
    body = "".join(chunks)
    assert "_italic_" in body


@pytest.mark.unit
def test_inline_code_preserved():
    chunks = TelegramFormatter.to_markdownv2_chunks("call `do_thing()` now")
    body = "".join(chunks)
    assert "`do_thing" in body


@pytest.mark.unit
def test_fenced_code_block_preserved():
    text = "before\n\n```python\ndef hi(): pass\n```\n\nafter"
    chunks = TelegramFormatter.to_markdownv2_chunks(text)
    body = "".join(chunks)
    assert "```" in body
    assert "def hi" in body


@pytest.mark.unit
def test_punctuation_escaped_outside_code():
    """MarkdownV2 requires escaping bare ``.`` and ``(`` ``)`` in body text."""
    chunks = TelegramFormatter.to_markdownv2_chunks("hello (world).")
    body = "".join(chunks)
    assert "\\(" in body
    assert "\\)" in body
    assert "\\." in body


@pytest.mark.unit
def test_long_text_is_split_under_4096_each():
    """Output chunks fit Telegram's 4096-byte message limit."""
    # Build something well past 4096 chars with plenty of structure so the
    # splitter has natural boundaries to cut on.
    text = ("paragraph with some words here.\n\n" * 300)
    chunks = TelegramFormatter.to_markdownv2_chunks(text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.encode("utf-16-le")) // 2 <= 4096


# ---------------------------------------------------------------------------
# file_caption()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_single_file_caption():
    caption = TelegramFormatter.file_caption(Path("report.pdf"))
    assert caption == "📎 report.pdf"


@pytest.mark.unit
def test_multi_file_caption_includes_index():
    caption = TelegramFormatter.file_caption(
        Path("/tmp/a.txt"), index=0, total=3,
    )
    assert caption == "📎 a.txt (1/3)"
    caption = TelegramFormatter.file_caption(
        Path("/tmp/b.txt"), index=2, total=3,
    )
    assert caption == "📎 b.txt (3/3)"
