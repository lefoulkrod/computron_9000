"""Unit tests for edit operations: replace_in_file and insert_text."""

from __future__ import annotations

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.edit_ops import insert_text, replace_in_file
from tools.virtual_computer.file_ops import write_file


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_replace_in_file_literal_and_regex() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("t.txt", "one two two three")
            r1 = replace_in_file("t.txt", "two", "TWO", regex=False)
            assert r1.success and r1.replacements == 2
            # verify file content after literal replacement
            after_r1 = Path(tmp_home, "t.txt").read_text(encoding="utf-8")
            assert after_r1 == "one TWO TWO three"
            r2 = replace_in_file("t.txt", r"TWO", "twO", regex=True)
            assert r2.success and r2.replacements == 2
            # verify file content after regex replacement
            after_r2 = Path(tmp_home, "t.txt").read_text(encoding="utf-8")
            assert after_r2 == "one twO twO three"


@pytest.mark.unit
def test_insert_text_after_before_replace() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("i.txt", "start\nKEY\nend\n")
            a = insert_text("i.txt", "KEY", "-A-", where="after", regex=False)
            assert a.success and a.occurrences == 1
            # verify after insertion after anchor
            after_a = Path(tmp_home, "i.txt").read_text(encoding="utf-8")
            assert after_a == "start\nKEY-A-\nend\n"
            b = insert_text("i.txt", "KEY", "-B-", where="before", regex=False)
            assert b.success and b.occurrences == 1
            # verify after insertion before anchor
            after_b = Path(tmp_home, "i.txt").read_text(encoding="utf-8")
            assert after_b == "start\n-B-KEY-A-\nend\n"
            c = insert_text("i.txt", "KEY", "-C-", where="replace", regex=False)
            assert c.success and c.occurrences == 1
            # verify after replace of anchor
            after_c = Path(tmp_home, "i.txt").read_text(encoding="utf-8")
            assert after_c == "start\n-B--C--A-\nend\n"


@pytest.mark.unit
def test_replace_in_file_preview_only_does_not_write() -> None:
    """Preview-only should report counts but leave file content unchanged."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("p.txt", "alpha beta beta gamma")
            res = replace_in_file("p.txt", "beta", "BETA", regex=False, preview_only=True)
            assert res.success is True
            assert res.preview is True
            assert res.replacements == 2
            # File content should be unchanged
            content = Path(tmp_home, "p.txt").read_text(encoding="utf-8")
            assert content == "alpha beta beta gamma"


@pytest.mark.unit
def test_replace_in_file_zero_replacements_no_write() -> None:
    """Zero replacements still returns success but does not alter file."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("z.txt", "no matches here")
            res = replace_in_file("z.txt", "absent", "X", regex=False)
            assert res.success is True
            assert res.replacements == 0
            content = Path(tmp_home, "z.txt").read_text(encoding="utf-8")
            assert content == "no matches here"


@pytest.mark.unit
def test_replace_in_file_file_not_found_and_binary() -> None:
    """Handle missing and binary files with clear errors."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Not found
            nf = replace_in_file("missing.txt", "a", "b")
            assert nf.success is False and nf.error == "file not found"
            assert nf.file_path == "missing.txt"

            # Binary file
            bin_path = Path(tmp_home, "bin.dat")
            bin_path.write_bytes(b"\x00\x01\x02binary\x00data")
            bf = replace_in_file("bin.dat", "a", "b")
            assert bf.success is False and bf.error == "binary file not supported"
            assert bf.file_path == "bin.dat"


@pytest.mark.unit
def test_insert_text_all_occurrences_literal_after() -> None:
    """Insert text after all literal anchor matches across content."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("multi.txt", "X_1 X_2\nX_3 X_4\n")
            res = insert_text(
                "multi.txt",
                "X_",
                "*",
                where="after",
                occurrences="all",
                regex=False,
            )
            assert res.success is True
            # There are 4 occurrences of "X_"
            assert res.occurrences == 4
            content = Path(tmp_home, "multi.txt").read_text(encoding="utf-8")
            assert content == "X_*1 X_*2\nX_*3 X_*4\n"


@pytest.mark.unit
def test_insert_text_regex_replace_all_digits() -> None:
    """Regex replace should transform all digit groups when occurrences=all."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("nums.txt", "v1 x v22 y 333z")
            res = insert_text(
                "nums.txt",
                r"\d+",
                "#",
                where="replace",
                occurrences="all",
                regex=True,
            )
            assert res.success is True
            # Matches: 1, 22, 333
            assert res.occurrences == 3
            content = Path(tmp_home, "nums.txt").read_text(encoding="utf-8")
            assert content == "v# x v# y #z"


@pytest.mark.unit
def test_insert_text_invalid_where_and_occurrences() -> None:
    """Invalid parameters should fail fast before touching the file system."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Invalid 'where'
            bad_where = insert_text("anything.txt", "A", "B", where="around", regex=False)
            assert bad_where.success is False
            assert bad_where.error == "invalid where"
            # Note: file_path echoes input path when validation fails early
            assert bad_where.file_path == "anything.txt"

            # Invalid 'occurrences'
            bad_occ = insert_text(
                "anything.txt", "A", "B", where="after", occurrences="many", regex=False
            )
            assert bad_occ.success is False
            assert bad_occ.error == "invalid occurrences"
            assert bad_occ.file_path == "anything.txt"


@pytest.mark.unit
def test_insert_text_anchor_not_found_and_file_not_found_and_binary() -> None:
    """Anchor not found returns error; not-found and binary files are handled."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Prepare a normal text file
            write_file("a.txt", "hello world\n")

            # Anchor not found
            miss = insert_text("a.txt", "XYZ", "!", where="after", regex=False)
            assert miss.success is False and miss.error == "anchor not found"
            # no changes
            content = Path(tmp_home, "a.txt").read_text(encoding="utf-8")
            assert content == "hello world\n"

            # File not found
            nf = insert_text("nope.txt", "hello", "!", where="after", regex=False)
            assert nf.success is False and nf.error == "file not found"
            assert nf.file_path == "nope.txt"

            # Binary file
            bin_path = Path(tmp_home, "bin2.dat")
            bin_path.write_bytes(b"\x00bin\x00")
            bf = insert_text("bin2.dat", "bin", "X", where="after", regex=False)
            assert bf.success is False and bf.error == "binary file not supported"
            assert bf.file_path == "bin2.dat"
