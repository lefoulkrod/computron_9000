"""Workspace resolution tests (container ↔ host mapping and traversal clamping)."""

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.workspace import set_workspace_folder
from tools.virtual_computer.file_ops import write_file, path_exists


class DummyVC:
    def __init__(self, home_dir: str, container_working_dir: str) -> None:
        self.home_dir = home_dir
        self.container_working_dir = container_working_dir


class DummyConfig1:
    def __init__(self, home_dir: str, container_working_dir: str) -> None:
        self.virtual_computer = DummyVC(home_dir, container_working_dir)


@pytest.mark.unit
def test_container_working_directory_is_remapped_to_host_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        set_workspace_folder("ws_123")
        cfg = DummyConfig1(tmp_home, "/home/computron")
    with mock.patch("config.load_config", return_value=cfg):
            p = "/home/computron/ws_123/src/app/module.py"
            res = write_file(p, "print('ok')\n")
            assert res.success, res.error
            expected = Path(tmp_home, "ws_123", "src", "app", "module.py")
            assert expected.exists(), f"Expected {expected} to exist"
            ex = path_exists(p)
            assert ex.exists and ex.is_file


@pytest.mark.unit
def test_parent_traversal_is_clamped() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        set_workspace_folder("ws_abc")
        cfg = DummyConfig1(tmp_home, "/home/computron")
    with mock.patch("config.load_config", return_value=cfg):
            p = "/home/computron/ws_abc/../../outside.txt"
            res = write_file(p, "x")
            assert res.success, res.error
            expected = Path(tmp_home, "ws_abc", "outside.txt")
            assert expected.exists(), f"Expected {expected} to exist"
