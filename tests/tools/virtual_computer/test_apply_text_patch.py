"""Unit tests for apply_text_patch utility."""

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
def test_apply_text_patch_line_replacement_includes_diff_and_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "line1\nline2\nline3\n")
            res = apply_text_patch(
                "file.txt",
                start_line=2,
                end_line=2,
                replacement="LINE_TWO_REPLACED\n",
            )
            assert res.success, res.error
            assert res.file_path == "file.txt"
            assert isinstance(res.diff, str)
            # With standard lineterm, headers are on separate lines
            assert res.diff.startswith("--- file.txt (before)\n+++ file.txt (after)\n@@ ")
            # Ensure expected removal/addition markers are present
            assert "-line2\n" in res.diff
            assert "+LINE_TWO_REPLACED\n" in res.diff

            new_content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert new_content == "line1\nLINE_TWO_REPLACED\nline3\n"


@pytest.mark.unit
def test_apply_text_patch_invalid_range_sets_error_and_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "only one line\n")
            res = apply_text_patch(
                "file.txt",
                start_line=2,
                end_line=2,
                replacement="oops\n",
            )
            assert not res.success
            assert res.file_path == "file.txt"
            assert res.diff is None
            assert res.error == "Invalid line range"


@pytest.mark.unit
def test_apply_text_patch_no_op_produces_empty_diff() -> None:
    """When replacement yields identical content, diff should be an empty string."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            original = "a\nb\nc\n"
            write_file("file.txt", original)
            # Replace line 2 with the same value
            res = apply_text_patch("file.txt", start_line=2, end_line=2, replacement="b\n")
            assert res.success
            assert res.file_path == "file.txt"
            assert res.diff == ""
            # File content should be unchanged
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content == original


@pytest.mark.unit
def test_apply_text_patch_exact_unified_diff_output() -> None:
    """Assert the full unified diff string for a simple single-line replacement."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "line1\nline2\nline3\n")
            res = apply_text_patch(
                "file.txt",
                start_line=2,
                end_line=2,
                replacement="LINE_TWO_REPLACED\n",
            )
            assert res.success, res.error
            expected = (
                "--- file.txt (before)\n"
                "+++ file.txt (after)\n"
                "@@ -1,3 +1,3 @@\n"
                " line1\n"
                "-line2\n"
                "+LINE_TWO_REPLACED\n"
                " line3\n"
            )
            assert res.diff == expected


@pytest.mark.unit
def test_apply_text_patch_multiline_replacement_expands_content_exact_diff() -> None:
    """Replace two lines with three lines; assert the full unified diff string."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "a\nb\nc\nd\n")
            res = apply_text_patch(
                "file.txt",
                start_line=2,
                end_line=3,
                replacement="B1\nB2\nB3\n",
            )
            assert res.success, res.error
            expected = (
                "--- file.txt (before)\n"
                "+++ file.txt (after)\n"
                "@@ -1,4 +1,5 @@\n"
                " a\n"
                "-b\n"
                "-c\n"
                "+B1\n"
                "+B2\n"
                "+B3\n"
                " d\n"
            )
            assert res.diff == expected


@pytest.mark.unit
def test_apply_text_patch_delete_middle_range_exact_diff() -> None:
    """Delete a middle range by replacing it with an empty string; assert exact diff."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "1\n2\n3\n4\n5\n")
            res = apply_text_patch(
                "file.txt",
                start_line=2,
                end_line=4,
                replacement="",
            )
            assert res.success, res.error
            expected = (
                "--- file.txt (before)\n"
                "+++ file.txt (after)\n"
                "@@ -1,5 +1,2 @@\n"
                " 1\n"
                "-2\n"
                "-3\n"
                "-4\n"
                " 5\n"
            )
            assert res.diff == expected


@pytest.mark.unit
def test_apply_text_patch_replace_last_line_with_multiple_lines_exact_diff() -> None:
    """Replace the final line with multiple lines; assert the full unified diff output."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "x\ny\nz\n")
            res = apply_text_patch(
                "file.txt",
                start_line=3,
                end_line=3,
                replacement="Z1\nZ2\n",
            )
            assert res.success, res.error
            expected = (
                "--- file.txt (before)\n"
                "+++ file.txt (after)\n"
                "@@ -1,3 +1,4 @@\n"
                " x\n"
                " y\n"
                "-z\n"
                "+Z1\n"
                "+Z2\n"
            )
            assert res.diff == expected
