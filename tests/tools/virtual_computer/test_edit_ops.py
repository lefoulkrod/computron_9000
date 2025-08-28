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
