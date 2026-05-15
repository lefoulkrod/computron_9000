"""Tests for apply_unified_diff utility."""

from pathlib import Path
import tempfile
import pytest

from tools.virtual_computer.patching import apply_unified_diff
from tools.virtual_computer.models import WriteFileResult
from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_apply_unified_diff_success() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "line1\nline2\n")
        diff = (
            "--- %(p)s\n+++ %(p)s\n"
            "@@ -1,2 +1,2 @@\n-line1\n-line2\n+line1MOD\n+line2\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        assert results and results[0].success
        content = Path(target).read_text(encoding="utf-8")
        assert content.startswith("line1MOD")


@pytest.mark.unit
def test_apply_unified_diff_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "missing.txt")
        diff = (
            "--- %(p)s\n+++ %(p)s\n"
            "@@ -1,1 +1,1 @@\n-line\n+line2\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        assert results and not results[0].success and results[0].error == "Target file missing"


@pytest.mark.unit
def test_apply_unified_diff_context_mismatch() -> None:
    """Hunk should fail when context line doesn't match current file."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "file.txt")
        write_file(target, "A\nB\nC\n")
        # Patch expects 'X' context which doesn't exist
        diff = (
            "--- %(p)s\n"
            "+++ %(p)s\n"
            "@@ -1,3 +1,3 @@\n"
            " X\n"  # wrong context
            "-B\n"
            "+BB\n"
            " C\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        assert results and not results[0].success
        assert "Context mismatch" in (results[0].error or "")


@pytest.mark.unit
def test_apply_unified_diff_multi_file_success() -> None:
    """Apply changes to two files in one diff."""
    with tempfile.TemporaryDirectory() as tmp_home:
        f1 = str(Path(tmp_home) / "f1.txt")
        f2 = str(Path(tmp_home) / "f2.txt")
        write_file(f1, "one\n")
        write_file(f2, "two\n")
        diff = (
            "--- %(f1)s\n"
            "+++ %(f1)s\n"
            "@@ -1,1 +1,1 @@\n"
            "-one\n"
            "+ONE\n"
            "--- %(f2)s\n"
            "+++ %(f2)s\n"
            "@@ -1,1 +1,1 @@\n"
            "-two\n"
            "+TWO\n"
        ) % {"f1": f1, "f2": f2}
        results = apply_unified_diff(diff)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert Path(f1).read_text(encoding="utf-8") == "ONE\n"
        assert Path(f2).read_text(encoding="utf-8") == "TWO\n"


@pytest.mark.unit
def test_apply_unified_diff_pure_deletion_not_supported() -> None:
    """Deletion (new file /dev/null) should fail as unsupported."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "del.txt")
        write_file(target, "data\n")
        diff = (
            "--- %(p)s\n"
            "+++ /dev/null\n"
            "@@ -1,1 +0,0 @@\n"
            "-data\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        # Implementation uses new path as target; /dev/null triggers unsupported
        assert results and not results[0].success
        assert "not supported" in (results[0].error or "")


@pytest.mark.unit
def test_apply_unified_diff_addition_only_unsupported() -> None:
    """New file creation should fail since existing file required."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "new.txt")
        diff = (
            "--- /dev/null\n"
            "+++ %(p)s\n"
            "@@ -0,0 +1,1 @@\n"
            "+hello\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        assert results and not results[0].success
        # Either unsupported creation or missing target depending on interpretation.
        err = results[0].error or ""
        assert ("not supported" in err) or ("Target file missing" in err)


@pytest.mark.unit
def test_apply_unified_diff_sequential_hunks_same_file() -> None:
    """Two hunks in one file should both apply."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "seq.txt")
        original = "a1\na2\na3\na4\na5\n"
        write_file(target, original)
        diff = (
            "--- %(p)s\n"
            "+++ %(p)s\n"
            "@@ -1,2 +1,2 @@\n"
            " a1\n"
            "-a2\n"
            "+A2\n"
            "@@ -4,2 +4,2 @@\n"
            " a4\n"
            "-a5\n"
            "+A5\n"
        ) % {"p": target}
        results = apply_unified_diff(diff)
        assert results and results[0].success
        assert Path(target).read_text(encoding="utf-8") == "a1\nA2\na3\na4\nA5\n"
