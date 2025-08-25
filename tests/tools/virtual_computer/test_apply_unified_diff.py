"""Tests for apply_unified_diff utility."""

from pathlib import Path
from unittest import mock
import tempfile
import pytest

from tools.virtual_computer.patching import apply_unified_diff
from tools.virtual_computer.models import WriteFileResult
from tools.virtual_computer.file_ops import write_file


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_apply_unified_diff_success() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "line1\nline2\n")
            diff = """--- a/file.txt\n+++ b/file.txt\n@@ -1,2 +1,2 @@\n-line1\n-line2\n+line1MOD\n+line2\n"""
            results = apply_unified_diff(diff)
            assert results and results[0].success
            content = Path(tmp_home, "file.txt").read_text(encoding="utf-8")
            assert content.startswith("line1MOD")


@pytest.mark.unit
def test_apply_unified_diff_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            diff = """--- a/missing.txt\n+++ b/missing.txt\n@@ -1,1 +1,1 @@\n-line\n+line2\n"""
            results = apply_unified_diff(diff)
            assert results and not results[0].success and results[0].error == "Target file missing"


@pytest.mark.unit
def test_apply_unified_diff_context_mismatch() -> None:
    """Hunk should fail when context line doesn't match current file."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("file.txt", "A\nB\nC\n")
            # Patch expects 'X' context which doesn't exist
            diff = (
                "--- a/file.txt\n"
                "+++ b/file.txt\n"
                "@@ -1,3 +1,3 @@\n"
                " X\n"  # wrong context
                "-B\n"
                "+BB\n"
                " C\n"
            )
            results = apply_unified_diff(diff)
            assert results and not results[0].success
            assert "Context mismatch" in (results[0].error or "")


@pytest.mark.unit
def test_apply_unified_diff_multi_file_success() -> None:
    """Apply changes to two files in one diff."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("f1.txt", "one\n")
            write_file("f2.txt", "two\n")
            diff = (
                "--- a/f1.txt\n"
                "+++ b/f1.txt\n"
                "@@ -1,1 +1,1 @@\n"
                "-one\n"
                "+ONE\n"
                "--- a/f2.txt\n"
                "+++ b/f2.txt\n"
                "@@ -1,1 +1,1 @@\n"
                "-two\n"
                "+TWO\n"
            )
            results = apply_unified_diff(diff)
            assert len(results) == 2
            assert all(r.success for r in results)
            assert Path(tmp_home, "f1.txt").read_text(encoding="utf-8") == "ONE\n"
            assert Path(tmp_home, "f2.txt").read_text(encoding="utf-8") == "TWO\n"


@pytest.mark.unit
def test_apply_unified_diff_pure_deletion_not_supported() -> None:
    """Deletion (new file /dev/null) should fail as unsupported."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("del.txt", "data\n")
            diff = (
                "--- a/del.txt\n"
                "+++ /dev/null\n"
                "@@ -1,1 +0,0 @@\n"
                "-data\n"
            )
            results = apply_unified_diff(diff)
            # Implementation uses new path as target; /dev/null triggers unsupported
            assert results and not results[0].success
            assert "not supported" in (results[0].error or "")


@pytest.mark.unit
def test_apply_unified_diff_addition_only_unsupported() -> None:
    """New file creation should fail since existing file required."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            diff = (
                "--- /dev/null\n"
                "+++ b/new.txt\n"
                "@@ -0,0 +1,1 @@\n"
                "+hello\n"
            )
            results = apply_unified_diff(diff)
            assert results and not results[0].success
            # Either unsupported creation or missing target depending on interpretation.
            err = results[0].error or ""
            assert ("not supported" in err) or ("Target file missing" in err)


@pytest.mark.unit
def test_apply_unified_diff_sequential_hunks_same_file() -> None:
    """Two hunks in one file should both apply."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            original = "a1\na2\na3\na4\na5\n"
            write_file("seq.txt", original)
            diff = (
                "--- a/seq.txt\n"
                "+++ b/seq.txt\n"
                "@@ -1,2 +1,2 @@\n"
                " a1\n"
                "-a2\n"
                "+A2\n"
                "@@ -4,2 +4,2 @@\n"
                " a4\n"
                "-a5\n"
                "+A5\n"
            )
            results = apply_unified_diff(diff)
            assert results and results[0].success
            assert Path(tmp_home, "seq.txt").read_text(encoding="utf-8") == "a1\nA2\na3\na4\nA5\n"
