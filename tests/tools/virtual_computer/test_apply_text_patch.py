"""Unit tests for apply_text_patch (old_text/new_text unique-match)."""

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.patching import apply_text_patch
from tools.virtual_computer.file_ops import write_file


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_apply_text_patch_single_match_succeeds() -> None:
    """Unique match should replace text and succeed."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "line1\nline2\nline3\n")
            res = apply_text_patch("file.txt", old_text="line2", new_text="LINE_TWO_REPLACED")
            assert res.success, res.error
            assert res.file_path == "file.txt"

            new_content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert new_content == "line1\nLINE_TWO_REPLACED\nline3\n"


@pytest.mark.unit
def test_apply_text_patch_no_match_returns_error() -> None:
    """Zero matches should fail with a descriptive error."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "only one line\n")
            res = apply_text_patch("file.txt", old_text="absent text", new_text="oops")
            assert not res.success
            assert res.file_path == "file.txt"
            assert "No match found" in (res.error or "")


@pytest.mark.unit
def test_apply_text_patch_multiple_matches_returns_error() -> None:
    """Multiple matches should fail with count in the error message."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "foo bar foo baz foo\n")
            res = apply_text_patch("file.txt", old_text="foo", new_text="qux")
            assert not res.success
            assert "3 matches" in (res.error or "")
            # File should be unchanged
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content == "foo bar foo baz foo\n"


@pytest.mark.unit
def test_apply_text_patch_no_op_produces_empty_diff() -> None:
    """When old_text equals new_text, succeed without writing."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            original = "a\nb\nc\n"
            write_file("file.txt", original)
            res = apply_text_patch("file.txt", old_text="b", new_text="b")
            assert res.success
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content == original


@pytest.mark.unit
def test_apply_text_patch_multiline_block() -> None:
    """Replace a multi-line block with different content."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "a\nb\nc\nd\n")
            res = apply_text_patch("file.txt", old_text="b\nc", new_text="B1\nB2\nB3")
            assert res.success, res.error
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content == "a\nB1\nB2\nB3\nd\n"


@pytest.mark.unit
def test_apply_text_patch_delete_block() -> None:
    """Delete a block by replacing with empty string."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "1\n2\n3\n4\n5\n")
            res = apply_text_patch("file.txt", old_text="2\n3\n4\n", new_text="")
            assert res.success, res.error
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content == "1\n5\n"


@pytest.mark.unit
def test_apply_text_patch_file_not_found() -> None:
    """Missing file should return error."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            res = apply_text_patch("missing.txt", old_text="a", new_text="b")
            assert not res.success
            assert "does not exist" in (res.error or "").lower()


@pytest.mark.unit
def test_apply_text_patch_whitespace_sensitive() -> None:
    """Matching is whitespace-sensitive — tabs vs spaces must be exact."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "    indented\n")
            # Wrong indentation should fail
            res = apply_text_patch("file.txt", old_text="\tindented", new_text="fixed")
            assert not res.success
            assert "No match found" in (res.error or "")
            # Correct indentation should succeed
            res2 = apply_text_patch("file.txt", old_text="    indented", new_text="fixed")
            assert res2.success


@pytest.mark.unit
def test_apply_text_patch_context_for_uniqueness() -> None:
    """Including surrounding context makes a non-unique match unique."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "def foo():\n    return 1\ndef bar():\n    return 1\n")
            # "return 1" alone matches twice
            res = apply_text_patch("file.txt", old_text="return 1", new_text="return 2")
            assert not res.success
            assert "2 matches" in (res.error or "")
            # Including context makes it unique
            res2 = apply_text_patch(
                "file.txt",
                old_text="def foo():\n    return 1",
                new_text="def foo():\n    return 2",
            )
            assert res2.success
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert "def foo():\n    return 2\n" in content
            assert "def bar():\n    return 1\n" in content
