"""Tests for read_file_or_dir_in_home_dir using a temporary directory and config mocking.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from typing import cast

from tools.virtual_computer.file_system import (
    read_file_or_dir_in_home_dir,
    ReadFileError,
    FileReadResult,
    DirectoryReadResult,
)

class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir
    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)

@pytest.mark.asyncio
@pytest.mark.unit
async def test_read_file_returns_text(tmp_path: Path):
    """Test reading a text file returns correct FileReadResult."""
    test_file = tmp_path / "foo.txt"
    test_content = "hello world"
    test_file.write_text(test_content, encoding="utf-8")
    with mock.patch("tools.virtual_computer.file_system.load_config", return_value=DummyConfig(str(tmp_path))):
        result = await read_file_or_dir_in_home_dir("foo.txt")
        assert isinstance(result, dict)
        assert result["type"] == "file"
        if result["type"] == "file":
            file_result = cast(FileReadResult, result)
            assert file_result["name"] == "foo.txt"
            assert file_result["content"] == test_content
            assert file_result["encoding"] == "utf-8"

@pytest.mark.asyncio
@pytest.mark.unit
async def test_read_file_returns_base64_for_binary(tmp_path: Path):
    """Test reading a binary file returns base64-encoded content."""
    test_file = tmp_path / "bar.bin"
    test_bytes = b"\x00\x01\x02\x03"
    test_file.write_bytes(test_bytes)
    with mock.patch("tools.virtual_computer.file_system.load_config", return_value=DummyConfig(str(tmp_path))):
        result = await read_file_or_dir_in_home_dir("bar.bin")
        assert isinstance(result, dict)
        assert result["type"] == "file"
        if result["type"] == "file":
            file_result = cast(FileReadResult, result)
            assert file_result["name"] == "bar.bin"
            assert file_result["encoding"] == "base64"
            import base64
            assert file_result["content"] == base64.b64encode(test_bytes).decode("ascii")

@pytest.mark.asyncio
@pytest.mark.unit
async def test_read_directory_lists_entries(tmp_path: Path):
    """Test reading a directory returns DirectoryReadResult with correct entries."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file1.txt").write_text("abc")
    (tmp_path / "subdir" / "file2.txt").write_text("def")
    with mock.patch("tools.virtual_computer.file_system.load_config", return_value=DummyConfig(str(tmp_path))):
        result = await read_file_or_dir_in_home_dir(".")
        assert isinstance(result, dict)
        assert result["type"] == "directory"
        if result["type"] == "directory":
            dir_result = cast(DirectoryReadResult, result)
            names = {entry["name"] for entry in dir_result["entries"]}
            assert "file1.txt" in names
            assert "subdir" in names
            subdir_entry = next(e for e in dir_result["entries"] if e["name"] == "subdir")
            assert subdir_entry["is_dir"] is True
            assert subdir_entry["is_file"] is False

@pytest.mark.asyncio
@pytest.mark.unit
async def test_read_file_or_dir_in_home_dir_not_found(tmp_path: Path):
    """Test that ReadFileError is raised for missing file or directory."""
    with mock.patch("tools.virtual_computer.file_system.load_config", return_value=DummyConfig(str(tmp_path))):
        with pytest.raises(ReadFileError):
            await read_file_or_dir_in_home_dir("does_not_exist.txt")
