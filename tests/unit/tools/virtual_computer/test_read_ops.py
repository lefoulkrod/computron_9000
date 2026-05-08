"""Unit tests for read operations: read_file, head, tail."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.read_ops import head, read_file, tail
from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_read_file_full_and_range() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "a.txt")
        write_file(target, "one\n two\nthree\n")
        full = read_file(target)
        # Content now includes cat-n style line numbers
        assert full.success
        assert full.content is not None
        assert "one\n" in full.content
        assert "two\n" in full.content
        assert "three\n" in full.content
        assert full.content.startswith("     1\t")
        r = read_file(target, start=2, end=2)
        assert r.success
        assert r.content is not None
        assert "two\n" in r.content
        assert r.content.startswith("     2\t")


@pytest.mark.unit
def test_head_and_tail_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "b.txt")
        lines = "".join(f"L{i}\n" for i in range(1, 11))
        write_file(target, lines)
        h = head(target, n=3)
        assert h.success
        assert h.content is not None
        assert "L1\n" in h.content
        assert "L3\n" in h.content
        assert "L4" not in h.content
        t = tail(target, n=2)
        assert t.success
        assert t.content is not None
        assert "L9\n" in t.content
        assert "L10\n" in t.content
        assert "L8" not in t.content
