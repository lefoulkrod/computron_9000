"""Integration test for write_file with absolute paths.

Tests writing a file in a temporary directory, ensuring correct file creation and cleanup.
"""

from pathlib import Path
import tempfile

import pytest

from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_write_file_creates_and_cleans_file():
    """Test write_file writes and cleans up a file in a temp directory."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "test_file.txt")
        test_content = "integration test content"

        # Write file
        res = write_file(target, test_content)
        assert res.success, res.error
        assert Path(target).exists(), "File was not created."
        assert Path(target).read_text(encoding="utf-8") == test_content

        # Cleanup
        Path(target).unlink()
        assert not Path(target).exists(), "File was not deleted after test."
