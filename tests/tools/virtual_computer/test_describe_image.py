"""Tests for the describe_image tool."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

# Load the module directly from file to avoid triggering __init__.py circular import
_spec = importlib.util.spec_from_file_location(
    "tools.virtual_computer.describe_image",
    str(Path(__file__).resolve().parents[3] / "tools" / "virtual_computer" / "describe_image.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
describe_image = _mod.describe_image


class _FakeVision:
    model = "vision-model"
    options = {}
    think = False


@pytest.fixture()
def mock_env(tmp_path):
    """Provide a mock config and temp directory for describe_image."""
    cfg = MagicMock()
    cfg.virtual_computer.home_dir = str(tmp_path)
    cfg.virtual_computer.container_working_dir = "/home/computron"
    cfg.llm.host = None
    cfg.vision = _FakeVision()
    with patch.object(_mod, "load_config", return_value=cfg):
        yield cfg, tmp_path


@pytest.mark.asyncio()
async def test_describe_image_invalid_path(mock_env):
    """Reject paths outside the container home."""
    result = await describe_image("/tmp/outside.png")
    assert "Error" in result
    assert "must be inside" in result


@pytest.mark.asyncio()
async def test_describe_image_file_not_found(mock_env):
    """Return error for missing files."""
    result = await describe_image("/home/computron/uploads/missing.png")
    assert "not found" in result


@pytest.mark.asyncio()
async def test_describe_image_unsupported_type(mock_env):
    """Return error for non-image file types."""
    _, tmp_path = mock_env
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "doc.pdf").write_bytes(b"fake pdf")
    result = await describe_image("/home/computron/uploads/doc.pdf")
    assert "Unsupported" in result


@pytest.mark.asyncio()
async def test_describe_image_success(mock_env):
    """Verify a successful vision model call returns the response text."""
    _, tmp_path = mock_env
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "test.png").write_bytes(b"fake png data")

    mock_response = MagicMock()
    mock_response.response = "A test image showing a cat."
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_response)

    with patch.object(_mod, "AsyncClient", return_value=mock_client):
        result = await describe_image("/home/computron/uploads/test.png", "What is in this image?")
        assert result == "A test image showing a cat."
        mock_client.generate.assert_called_once()
