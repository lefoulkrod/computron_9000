"""Verify that file ops always resolve under the globally-set workspace.

Covers absolute-path sanitization and relative path handling for write/append/mkdir.
"""

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.file_ops import (
    write_file,
    append_to_file,
    make_dirs,
    _read_file_directory,
)
from tools.virtual_computer.workspace import (
    set_workspace_folder,
    get_current_workspace_folder,
)


class DummyConfig2:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_writes_stay_under_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        set_workspace_folder("ws_123")
        assert get_current_workspace_folder() == "ws_123"
    with mock.patch("config.load_config", return_value=DummyConfig2(tmp_home)):
            abs_like_path = "/etc/../danger/../../not_real/escape.txt"
            res = write_file(abs_like_path, "safe")
            assert res.success, res.error
            rel_path = res.file_path
            assert rel_path.startswith("ws_123/")
            expected = Path(tmp_home, rel_path)
            assert expected.exists()

            mk = make_dirs("pkg/sub")
            assert mk.success
            assert Path(tmp_home, "ws_123", "pkg", "sub").exists()

            res2 = append_to_file("pkg/sub/file.txt", "x")
            assert res2.success
            assert Path(tmp_home, "ws_123", "pkg", "sub", "file.txt").exists()

            rf = _read_file_directory("pkg/sub/file.txt")
            assert rf.type == "file"
            assert rf.name.startswith("ws_123/")
