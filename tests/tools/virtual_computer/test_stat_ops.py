"""Unit tests for stat_ops wrappers: exists, is_file, is_dir."""

from __future__ import annotations

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.stat_ops import exists, is_dir, is_file
from tools.virtual_computer.file_ops import write_file, make_dirs


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_exists_file_and_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("c.txt", "x")
            make_dirs("pkg/sub")
            assert exists("c.txt").exists
            assert is_file("c.txt").is_file
            assert is_dir("pkg").is_dir
