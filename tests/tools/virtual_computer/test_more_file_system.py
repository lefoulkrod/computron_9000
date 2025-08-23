"""Tests for new virtual computer file system helpers.

Covers: make_dirs, append_to_file, path_exists, copy_path, move_path, remove_path.
"""

from pathlib import Path
from unittest import mock
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


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)

@pytest.mark.unit
def test_file_helpers_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create nested directories
            res_mkdir = make_dirs("pkg/module")
            assert res_mkdir.success
            assert Path(tmp_home, "pkg", "module").exists()

            # Write then append to a file
            res_write = write_file("pkg/module/file.txt", "x")
            assert res_write.success
            res_append = append_to_file("pkg/module/file.txt", "y")
            assert res_append.success
            content = Path(tmp_home, "pkg", "module", "file.txt").read_text(encoding="utf-8")
            assert content == "xy"

            # Existence check
            exists_info = path_exists("pkg/module/file.txt")
            assert exists_info.exists and exists_info.is_file and not exists_info.is_dir

            # Copy and move
            res_copy = copy_path("pkg/module/file.txt", "pkg/module/file2.txt")
            assert res_copy.success
            assert Path(tmp_home, "pkg", "module", "file2.txt").exists()
            res_move = move_path("pkg/module/file2.txt", "pkg/file2moved.txt")
            assert res_move.success
            assert Path(tmp_home, "pkg", "file2moved.txt").exists()

            # Remove recursively
            res_rm = remove_path("pkg")
            assert res_rm.success
            assert not Path(tmp_home, "pkg").exists()
