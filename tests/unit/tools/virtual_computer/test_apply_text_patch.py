"""Unit tests for apply_text_patch (old_text/new_text unique-match)."""

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.patching import apply_text_patch
from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_apply_text_patch_single_match_succeeds() -> None:
    """Unique match should replace text and succeed."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "line1\nline2\nline3\n")
        res = apply_text_patch(target, old_text="line2", new_text="LINE_TWO_REPLACED")
        assert res.success, res.error
        assert res.file_path == target

        new_content = Path(target).read_text(encoding="utf-8")
        assert new_content == "line1\nLINE_TWO_REPLACED\nline3\n"


@pytest.mark.unit
def test_apply_text_patch_no_match_returns_error() -> None:
    """Zero matches should fail with a descriptive error."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "only one line\n")
        res = apply_text_patch(target, old_text="absent text", new_text="oops")
        assert not res.success
        assert res.file_path == target
        assert "No match found" in (res.error or "")


@pytest.mark.unit
def test_apply_text_patch_multiple_matches_returns_error() -> None:
    """Multiple matches should fail with count in the error message."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "foo bar foo baz foo\n")
        res = apply_text_patch(target, old_text="foo", new_text="qux")
        assert not res.success
        assert "3 matches" in (res.error or "")
        # File should be unchanged
        content = Path(target).read_text(encoding="utf-8")
        assert content == "foo bar foo baz foo\n"


@pytest.mark.unit
def test_apply_text_patch_no_op_produces_empty_diff() -> None:
    """When old_text equals new_text, succeed without writing."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        original = "a\nb\nc\n"
        write_file(target, original)
        res = apply_text_patch(target, old_text="b", new_text="b")
        assert res.success
        content = Path(target).read_text(encoding="utf-8")
        assert content == original


@pytest.mark.unit
def test_apply_text_patch_multiline_block() -> None:
    """Replace a multi-line block with different content."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "a\nb\nc\nd\n")
        res = apply_text_patch(target, old_text="b\nc", new_text="B1\nB2\nB3")
        assert res.success, res.error
        content = Path(target).read_text(encoding="utf-8")
        assert content == "a\nB1\nB2\nB3\nd\n"


@pytest.mark.unit
def test_apply_text_patch_delete_block() -> None:
    """Delete a block by replacing with empty string."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "1\n2\n3\n4\n5\n")
        res = apply_text_patch(target, old_text="2\n3\n4\n", new_text="")
        assert res.success, res.error
        content = Path(target).read_text(encoding="utf-8")
        assert content == "1\n5\n"


@pytest.mark.unit
def test_apply_text_patch_file_not_found() -> None:
    """Missing file should return error."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "missing.txt")
        res = apply_text_patch(target, old_text="a", new_text="b")
        assert not res.success
        assert "does not exist" in (res.error or "").lower()


@pytest.mark.unit
def test_apply_text_patch_whitespace_sensitive() -> None:
    """Matching is whitespace-sensitive — tabs vs spaces must be exact."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "    indented\n")
        # Wrong indentation should fail
        res = apply_text_patch(target, old_text="\tindented", new_text="fixed")
        assert not res.success
        assert "No match found" in (res.error or "")
        # Correct indentation should succeed
        res2 = apply_text_patch(target, old_text="    indented", new_text="fixed")
        assert res2.success


@pytest.mark.unit
def test_apply_text_patch_context_for_uniqueness() -> None:
    """Including surrounding context makes a non-unique match unique."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "def foo():\n    return 1\ndef bar():\n    return 1\n")
        # "return 1" alone matches twice
        res = apply_text_patch(target, old_text="return 1", new_text="return 2")
        assert not res.success
        assert "2 matches" in (res.error or "")
        # Including context makes it unique
        res2 = apply_text_patch(
            target,
            old_text="def foo():\n    return 1",
            new_text="def foo():\n    return 2",
        )
        assert res2.success
        content = Path(target).read_text(encoding="utf-8")
        assert "def foo():\n    return 2\n" in content
        assert "def bar():\n    return 1\n" in content
