"""Tests for prepend_to_file helper.

Covers: create, prepend semantics, and workspace scoping.
"""

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.file_ops import (
    write_file,
    prepend_to_file,
    _read_file_directory,
)
from tools.virtual_computer.workspace import (
    set_workspace_folder,
    get_current_workspace_folder,
    reset_workspace_folder,
)


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_prepend_creates_and_prepends_text() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create new file by prepending
            res = prepend_to_file("pkg/file.txt", "B")
            assert res.success, res.error
            p = Path(tmp_home, res.file_path)
            assert p.exists()
            assert p.read_text(encoding="utf-8") == "B"

            # Prepend onto existing content
            res2 = prepend_to_file("pkg/file.txt", "A")
            assert res2.success
            assert p.read_text(encoding="utf-8") == "AB"

            # Prepend after a write
            res3 = write_file("pkg/other.txt", "YZ")
            assert res3.success
            p2 = Path(tmp_home, res3.file_path)
            res4 = prepend_to_file("pkg/other.txt", "X")
            assert res4.success
            assert p2.read_text(encoding="utf-8") == "XYZ"


@pytest.mark.unit
def test_prepend_respects_workspace_scope() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        prev = get_current_workspace_folder()
        try:
            set_workspace_folder("ws_abc")
            with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
                res = prepend_to_file("dir/sub.txt", "1")
                assert res.success
                # file should be under the active workspace folder
                p = Path(tmp_home, res.file_path)
                assert p.exists()

                rf = _read_file_directory("dir/sub.txt")
                assert rf.type == "file"
                assert rf.name.startswith("ws_abc/")
        finally:
            if prev is None:
                reset_workspace_folder()
            else:
                set_workspace_folder(prev)
