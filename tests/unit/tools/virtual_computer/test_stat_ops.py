"""Unit tests for stat_ops wrappers: exists, is_file, is_dir."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.stat_ops import exists, is_dir, is_file
from tools.virtual_computer.file_ops import write_file, make_dirs


@pytest.mark.unit
def test_exists_file_and_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        f = str(Path(tmp_home) / "c.txt")
        d = str(Path(tmp_home) / "pkg" / "sub")
        write_file(f, "x")
        make_dirs(d)
        assert exists(f).exists
        assert is_file(f).is_file
        assert is_dir(str(Path(tmp_home) / "pkg")).is_dir
