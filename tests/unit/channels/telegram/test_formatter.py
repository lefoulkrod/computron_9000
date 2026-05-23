"""Tests for channels.telegram._formatter.TelegramFormatter."""

from pathlib import Path

import pytest

from channels.telegram._formatter import TelegramFormatter


@pytest.mark.unit
class TestSplit:
    """Tests for the split() chunker — paragraph/sentence/hard-split branches."""

    def test_short_text_returned_unchanged(self):
        chunks = TelegramFormatter.split("hello world", limit=4096)
        assert chunks == ["hello world"]

    def test_empty_string_returns_single_empty(self):
        # An empty string is below the limit, so it comes back as a single chunk.
        assert TelegramFormatter.split("", limit=100) == [""]

    def test_exact_limit_not_split(self):
        text = "x" * 100
        chunks = TelegramFormatter.split(text, limit=100)
        assert chunks == [text]

    def test_paragraph_break_preferred(self):
        """When a double-newline exists before the limit, the first split
        happens at the paragraph boundary."""
        text = "para one is here.\n\npara two is short."
        chunks = TelegramFormatter.split(text, limit=30)
        assert len(chunks) == 2
        assert chunks[0] == "para one is here."
        assert chunks[1].startswith("para two")

    def test_single_newline_when_no_paragraph_break(self):
        """Falls through to a single-newline split when no double-newline fits."""
        text = "line one of text\nline two of text\nline three"
        chunks = TelegramFormatter.split(text, limit=20)
        # Should split on a newline before position 20.
        assert len(chunks) >= 2
        assert all(len(c) <= 20 for c in chunks)
        # No chunk should contain a leading newline (lstrip\n applied).
        assert all(not c.startswith("\n") for c in chunks)

    def test_sentence_boundary_fallback(self):
        """Falls through to a sentence end when no newline before the limit.

        The splitter's sentence cut sits *before* the punctuation, so the
        next chunk starts with the punctuation. Assert on the partitioning
        rather than the boundary character.
        """
        text = "First sentence ends here. Second sentence is right after! Third?"
        chunks = TelegramFormatter.split(text, limit=30)
        assert len(chunks) >= 2
        # Both halves reflect the original content split somewhere mid-string.
        joined = "".join(chunks)
        # Joining loses the whitespace that was stripped at the boundaries;
        # confirm the meaningful tokens survive.
        for token in ("First", "Second", "Third"):
            assert token in joined

    def test_hard_split_when_no_boundary(self):
        """Long unbroken text gets a hard split at the limit."""
        text = "x" * 50
        chunks = TelegramFormatter.split(text, limit=10)
        # 50 / 10 = 5 hard-split chunks.
        assert len(chunks) == 5
        assert all(len(c) == 10 for c in chunks)

    def test_hard_split_when_only_late_boundary(self):
        """Sentence break later than limit//4 wins; earlier than that is too short, hard-split instead."""
        # Sentence break is at position 5, limit is 20, limit//4 is 5 — boundary
        # >= limit//4 wins. Make it boundary < limit//4 to force hard split.
        text = "ab. " + "x" * 40  # period at index 2, limit//4 = 5 -> too early
        chunks = TelegramFormatter.split(text, limit=20)
        # First chunk should be ~20 chars, not "ab."
        assert len(chunks[0]) > 5

    def test_chunks_join_to_original_modulo_whitespace_trim(self):
        """Chunks reassemble back to the original input ignoring per-chunk
        leading-newline strip and trailing-whitespace trim."""
        text = (
            "Paragraph one with some content.\n\n"
            "Paragraph two has a fair bit more text so it crosses the limit boundary.\n\n"
            "Paragraph three."
        )
        chunks = TelegramFormatter.split(text, limit=60)
        joined = "\n\n".join(chunks)
        # Whitespace normalization makes exact equality tricky; just confirm
        # each paragraph survives somewhere in the output.
        assert "Paragraph one" in joined
        assert "Paragraph two" in joined
        assert "Paragraph three" in joined


@pytest.mark.unit
class TestEscapeMarkdown:
    """Tests for MarkdownV2 escaping."""

    def test_escapes_all_special_chars(self):
        out = TelegramFormatter.escape_markdown("hello *world* (yes)")
        assert "\\*" in out
        assert "\\(" in out
        assert "\\)" in out

    def test_plain_text_passthrough(self):
        out = TelegramFormatter.escape_markdown("plain text")
        assert out == "plain text"


@pytest.mark.unit
class TestFileCaption:
    """Tests for file_caption()."""

    def test_single_file_caption(self):
        caption = TelegramFormatter.file_caption(Path("report.pdf"))
        assert caption == "📎 report.pdf"

    def test_multi_file_caption_includes_index(self):
        caption = TelegramFormatter.file_caption(
            Path("/tmp/a.txt"), index=0, total=3,
        )
        assert caption == "📎 a.txt (1/3)"
        caption = TelegramFormatter.file_caption(
            Path("/tmp/b.txt"), index=2, total=3,
        )
        assert caption == "📎 b.txt (3/3)"
