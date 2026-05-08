"""Tests for new virtual computer file system helpers.

Covers: make_dirs, append_to_file, path_exists, copy_path, move_path, remove_path.
"""

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.file_ops import (
    append_to_file,
    copy_path,
    make_dirs,
    move_path,
    path_exists,
    remove_path,
    write_file,
)


@pytest.mark.unit
def test_file_helpers_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        pkg_mod = str(Path(tmp_home) / "pkg" / "module")

        # Create nested directories
        res_mkdir = make_dirs(pkg_mod)
        assert res_mkdir.success
        assert Path(pkg_mod).exists()

        # Write then append to a file
        f = str(Path(pkg_mod) / "file.txt")
        res_write = write_file(f, "x")
        assert res_write.success
        res_append = append_to_file(f, "y")
        assert res_append.success
        content = Path(f).read_text(encoding="utf-8")
        assert content == "xy"

        # Existence check
        exists_info = path_exists(f)
        assert exists_info.exists and exists_info.is_file and not exists_info.is_dir

        # Copy and move
        f2 = str(Path(pkg_mod) / "file2.txt")
        res_copy = copy_path(f, f2)
        assert res_copy.success
        assert Path(f2).exists()
        f2moved = str(Path(tmp_home) / "pkg" / "file2moved.txt")
        res_move = move_path(f2, f2moved)
        assert res_move.success
        assert Path(f2moved).exists()

        # Remove recursively
        pkg_dir = str(Path(tmp_home) / "pkg")
        res_rm = remove_path(pkg_dir)
        assert res_rm.success
        assert not Path(pkg_dir).exists()
