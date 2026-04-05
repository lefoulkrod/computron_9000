"""Tests for prepend_to_file helper."""

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.file_ops import (
    write_file,
    prepend_to_file,
)


@pytest.mark.unit
def test_prepend_creates_and_prepends_text() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "pkg" / "file.txt")

        # Create new file by prepending
        res = prepend_to_file(target, "B")
        assert res.success, res.error
        assert Path(target).read_text(encoding="utf-8") == "B"

        # Prepend onto existing content
        res2 = prepend_to_file(target, "A")
        assert res2.success
        assert Path(target).read_text(encoding="utf-8") == "AB"

        # Prepend after a write
        target2 = str(Path(tmp_home) / "pkg" / "other.txt")
        res3 = write_file(target2, "YZ")
        assert res3.success
        res4 = prepend_to_file(target2, "X")
        assert res4.success
        assert Path(target2).read_text(encoding="utf-8") == "XYZ"
