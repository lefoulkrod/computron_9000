"""Integration test for write_file_in_home_dir with config mocking.

Tests writing a file in the virtual computer's home directory, ensuring correct file creation and cleanup.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from tools.virtual_computer.file_system import write_file_in_home_dir

class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir
    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)

@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_file_in_home_dir_creates_and_cleans_file():
    """Test write_file_in_home_dir writes and cleans up a file in the mocked home dir.

    Args:
        None
    Returns:
        None
    Raises:
        AssertionError: If file is not written or not cleaned up.
    """
    with tempfile.TemporaryDirectory() as tmp_home:
        test_file = "test_integration_file.txt"
        test_content = "integration test content"
        file_path = Path(tmp_home) / test_file
        with mock.patch("tools.virtual_computer.file_system.load_config", return_value=DummyConfig(tmp_home)):
            # Write file
            write_file_in_home_dir(test_file, test_content)
            assert file_path.exists(), "File was not created in the mocked home dir."
            with file_path.open("r", encoding="utf-8") as f:
                assert f.read() == test_content, "File content does not match."
            # Cleanup
            file_path.unlink()
            assert not file_path.exists(), "File was not deleted after test."
