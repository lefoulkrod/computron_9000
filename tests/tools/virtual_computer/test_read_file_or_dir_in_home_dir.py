"""Tests for read_file_or_dir_in_home_dir using a temporary directory and config mocking.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from typing import cast

from tools.virtual_computer.file_ops import _read_file_directory, list_dir
from tools.virtual_computer.models import ReadFileError, FileReadResult, DirectoryReadResult

class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir
    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)

@pytest.mark.unit
def test_read_file_returns_text(tmp_path: Path):
    """Test reading a text file returns correct FileReadResult."""
    test_file = tmp_path / "foo.txt"
    test_content = "hello world"
    test_file.write_text(test_content, encoding="utf-8")
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = _read_file_directory("foo.txt")
        assert isinstance(result, FileReadResult)
        assert result.type == "file"
        assert result.name == "foo.txt"
        assert result.content == test_content
        assert result.encoding == "utf-8"

@pytest.mark.unit
def test_read_file_returns_base64_for_binary(tmp_path: Path):
    """Test reading a binary file returns base64-encoded content."""
    test_file = tmp_path / "bar.bin"
    test_bytes = b"\x00\x01\x02\x03"
    test_file.write_bytes(test_bytes)
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = _read_file_directory("bar.bin")
        assert isinstance(result, FileReadResult)
        assert result.type == "file"
        assert result.name == "bar.bin"
        assert result.encoding == "base64"
        import base64
        assert result.content == base64.b64encode(test_bytes).decode("ascii")

@pytest.mark.unit
def test_read_directory_lists_entries(tmp_path: Path):
    """Test reading a directory returns DirectoryReadResult with correct entries."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file1.txt").write_text("abc")
    (tmp_path / "subdir" / "file2.txt").write_text("def")
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = _read_file_directory(".")
        assert isinstance(result, DirectoryReadResult)
        assert result.type == "directory"
        names = {entry.name for entry in result.entries}
        assert "file1.txt" in names
        assert "subdir" in names
        subdir_entry = next(e for e in result.entries if e.name == "subdir")
        assert subdir_entry.is_dir is True
        assert subdir_entry.is_file is False

@pytest.mark.unit
def test_read_file_or_dir_in_home_dir_not_found(tmp_path: Path):
    """Test that ReadFileError is raised for missing file or directory."""
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        with pytest.raises(ReadFileError):
            _read_file_directory("does_not_exist.txt")


@pytest.mark.unit
def test_list_dir_without_hidden_files(tmp_path: Path):
    """Test list_dir excludes hidden files by default.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If hidden files are included when they shouldn't be.
    """
    # Create test files and directories
    (tmp_path / "visible_file.txt").write_text("content")
    (tmp_path / ".hidden_file.txt").write_text("secret")
    (tmp_path / "visible_dir").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = list_dir(".", include_hidden=False)
        
        assert isinstance(result, DirectoryReadResult)
        assert result.type == "directory"
        
        entry_names = {entry.name for entry in result.entries}
        assert "visible_file.txt" in entry_names
        assert "visible_dir" in entry_names
        assert ".hidden_file.txt" not in entry_names
        assert ".hidden_dir" not in entry_names


@pytest.mark.unit
def test_list_dir_with_hidden_files(tmp_path: Path):
    """Test list_dir includes hidden files when include_hidden=True.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If hidden files are excluded when they should be included.
    """
    # Create test files and directories
    (tmp_path / "visible_file.txt").write_text("content")
    (tmp_path / ".hidden_file.txt").write_text("secret")
    (tmp_path / "visible_dir").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = list_dir(".", include_hidden=True)
        
        assert isinstance(result, DirectoryReadResult)
        assert result.type == "directory"
        
        entry_names = {entry.name for entry in result.entries}
        assert "visible_file.txt" in entry_names
        assert "visible_dir" in entry_names
        assert ".hidden_file.txt" in entry_names
        assert ".hidden_dir" in entry_names


@pytest.mark.unit
def test_list_dir_preserves_entry_types(tmp_path: Path):
    """Test list_dir preserves correct file vs directory types.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If entry types are incorrect.
    """
    (tmp_path / "test_file.txt").write_text("content")
    (tmp_path / "test_dir").mkdir()
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = list_dir(".")
        
        file_entry = next(e for e in result.entries if e.name == "test_file.txt")
        dir_entry = next(e for e in result.entries if e.name == "test_dir")
        
        assert file_entry.is_file is True
        assert file_entry.is_dir is False
        assert dir_entry.is_file is False
        assert dir_entry.is_dir is True


@pytest.mark.unit
def test_list_dir_on_file_raises_error(tmp_path: Path):
    """Test list_dir raises ReadFileError when called on a file.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If ReadFileError is not raised for files.
    """
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("content")
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        with pytest.raises(ReadFileError, match="Path is not a directory"):
            list_dir("test_file.txt")


@pytest.mark.unit
def test_list_dir_on_nonexistent_path_raises_error(tmp_path: Path):
    """Test list_dir raises ReadFileError for nonexistent paths.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If ReadFileError is not raised for missing paths.
    """
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        with pytest.raises(ReadFileError, match="Path does not exist"):
            list_dir("nonexistent_directory")


@pytest.mark.unit
def test_list_dir_empty_directory(tmp_path: Path):
    """Test list_dir handles empty directories correctly.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If empty directory is not handled correctly.
    """
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        result = list_dir("empty")
        
        assert isinstance(result, DirectoryReadResult)
        assert result.type == "directory"
        assert result.name == "empty"
        assert len(result.entries) == 0


@pytest.mark.unit
def test_list_dir_subdirectory(tmp_path: Path):
    """Test list_dir works with subdirectories.
    
    Args:
        tmp_path: Temporary directory fixture.
        
    Returns:
        None
        
    Raises:
        AssertionError: If subdirectory listing fails.
    """
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file_in_subdir.txt").write_text("content")
    (subdir / ".hidden_in_subdir.txt").write_text("hidden")
    
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        # Test without hidden files
        result = list_dir("subdir", include_hidden=False)
        entry_names = {entry.name for entry in result.entries}
        assert "file_in_subdir.txt" in entry_names
        assert ".hidden_in_subdir.txt" not in entry_names
        
        # Test with hidden files
        result_with_hidden = list_dir("subdir", include_hidden=True)
        entry_names_with_hidden = {entry.name for entry in result_with_hidden.entries}
        assert "file_in_subdir.txt" in entry_names_with_hidden
        assert ".hidden_in_subdir.txt" in entry_names_with_hidden
