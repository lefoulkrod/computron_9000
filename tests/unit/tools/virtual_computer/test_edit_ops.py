"""Unit tests for edit operations: replace_in_file and insert_text."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.edit_ops import insert_text, replace_in_file
from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_replace_in_file_literal() -> None:
    """Literal replacement replaces all occurrences."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "t.txt")
        write_file(target, "one two two three")
        r1 = replace_in_file(target, "two", "TWO")
        assert r1.success and r1.replacements == 2
        after_r1 = Path(target).read_text(encoding="utf-8")
        assert after_r1 == "one TWO TWO three"


@pytest.mark.unit
def test_insert_text_after_before_replace() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "i.txt")
        write_file(target, "start\nKEY\nend\n")
        a = insert_text(target, "KEY", "-A-", where="after")
        assert a.success and a.occurrences == 1
        after_a = Path(target).read_text(encoding="utf-8")
        assert after_a == "start\nKEY-A-\nend\n"
        b = insert_text(target, "KEY", "-B-", where="before")
        assert b.success and b.occurrences == 1
        after_b = Path(target).read_text(encoding="utf-8")
        assert after_b == "start\n-B-KEY-A-\nend\n"
        c = insert_text(target, "KEY", "-C-", where="replace")
        assert c.success and c.occurrences == 1
        after_c = Path(target).read_text(encoding="utf-8")
        assert after_c == "start\n-B--C--A-\nend\n"


@pytest.mark.unit
def test_replace_in_file_zero_replacements_no_write() -> None:
    """Zero replacements still returns success but does not alter file."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "z.txt")
        write_file(target, "no matches here")
        res = replace_in_file(target, "absent", "X")
        assert res.success is True
        assert res.replacements == 0
        content = Path(target).read_text(encoding="utf-8")
        assert content == "no matches here"


@pytest.mark.unit
def test_replace_in_file_file_not_found_and_binary() -> None:
    """Handle missing and binary files with clear errors."""
    with tempfile.TemporaryDirectory() as tmp_home:
        missing = str(Path(tmp_home) / "missing.txt")
        nf = replace_in_file(missing, "a", "b")
        assert nf.success is False and nf.error == "file not found"
        assert nf.file_path == missing

        bin_path = str(Path(tmp_home) / "bin.dat")
        Path(bin_path).write_bytes(b"\x00\x01\x02binary\x00data")
        bf = replace_in_file(bin_path, "a", "b")
        assert bf.success is False and bf.error == "binary file not supported"
        assert bf.file_path == bin_path


@pytest.mark.unit
def test_insert_text_all_occurrences_literal_after() -> None:
    """Insert text after all literal anchor matches across content."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "multi.txt")
        write_file(target, "X_1 X_2\nX_3 X_4\n")
        res = insert_text(
            target,
            "X_",
            "*",
            where="after",
            occurrences="all",
        )
        assert res.success is True
        assert res.occurrences == 4
        content = Path(target).read_text(encoding="utf-8")
        assert content == "X_*1 X_*2\nX_*3 X_*4\n"


@pytest.mark.unit
def test_insert_text_invalid_where_and_occurrences() -> None:
    """Invalid parameters should fail fast before touching the file system."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "anything.txt")
        bad_where = insert_text(target, "A", "B", where="around")
        assert bad_where.success is False
        assert bad_where.error == "invalid where"
        assert bad_where.file_path == target

        bad_occ = insert_text(
            target, "A", "B", where="after", occurrences="many"
        )
        assert bad_occ.success is False
        assert bad_occ.error == "invalid occurrences"
        assert bad_occ.file_path == target


@pytest.mark.unit
def test_insert_text_anchor_not_found_and_file_not_found_and_binary() -> None:
    """Anchor not found returns error; not-found and binary files are handled."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "a.txt")
        write_file(target, "hello world\n")

        miss = insert_text(target, "XYZ", "!", where="after")
        assert miss.success is False and miss.error == "anchor not found"
        content = Path(target).read_text(encoding="utf-8")
        assert content == "hello world\n"

        nope = str(Path(tmp_home) / "nope.txt")
        nf = insert_text(nope, "hello", "!", where="after")
        assert nf.success is False and nf.error == "file not found"
        assert nf.file_path == nope

        bin_path = str(Path(tmp_home) / "bin2.dat")
        Path(bin_path).write_bytes(b"\x00bin\x00")
        bf = insert_text(bin_path, "bin", "X", where="after")
        assert bf.success is False and bf.error == "binary file not supported"
        assert bf.file_path == bin_path
