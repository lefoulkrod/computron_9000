"""Tests for the receive_attachment function."""

import base64
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

# Load the module directly from file to avoid triggering __init__.py circular import
_spec = importlib.util.spec_from_file_location(
    "tools.virtual_computer.receive_file",
    str(Path(__file__).resolve().parents[3] / "tools" / "virtual_computer" / "receive_file.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
receive_attachment = _mod.receive_attachment


@pytest.fixture()
def mock_config(tmp_path):
    """Provide a mock config pointing at a temp directory."""
    cfg = MagicMock()
    cfg.virtual_computer.home_dir = str(tmp_path)
    with patch.object(_mod, "load_config", return_value=cfg):
        yield cfg, tmp_path


def test_receive_attachment_writes_file(mock_config):
    """Verify that a file is decoded and written to the uploads directory."""
    _, tmp_path = mock_config
    content = b"hello world"
    encoded = base64.b64encode(content).decode()
    path = receive_attachment(encoded, "text/plain", "hello.txt")
    assert path == str(tmp_path / "uploads" / "hello.txt")
    assert (tmp_path / "uploads" / "hello.txt").read_bytes() == content


def test_receive_attachment_generates_name_when_missing(mock_config):
    """Verify that a UUID-based name with correct extension is generated."""
    _, tmp_path = mock_config
    content = b"PNG data"
    encoded = base64.b64encode(content).decode()
    path = receive_attachment(encoded, "image/png")
    assert path.startswith(str(tmp_path / "uploads"))
    assert path.endswith(".png")
    filename = Path(path).name
    assert (tmp_path / "uploads" / filename).exists()


def test_receive_attachment_handles_collision(mock_config):
    """Verify that colliding filenames get a unique suffix."""
    _, tmp_path = mock_config
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "test.txt").write_bytes(b"existing")
    content = b"new content"
    encoded = base64.b64encode(content).decode()
    path = receive_attachment(encoded, "text/plain", "test.txt")
    assert path != str(tmp_path / "uploads" / "test.txt")
    assert "test_" in path
