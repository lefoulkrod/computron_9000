"""Tests for the describe_image tool."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

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


_FAKE_SETTINGS = {
    "vision_model": "vision-model",
    "vision_options": {},
    "vision_think": False,
}


async def _fake_vision_generate(prompt, image_base64, *, media_type="image/png"):
    return "A test image showing a cat."


@pytest.fixture()
def mock_env(tmp_path):
    """Provide a mock environment for describe_image."""
    with patch("settings.load_settings", return_value=dict(_FAKE_SETTINGS)):
        yield tmp_path


@pytest.mark.asyncio()
async def test_describe_image_file_not_found(mock_env):
    """Return error for missing files."""
    tmp_path = mock_env
    target = str(tmp_path / "missing.png")
    result = await describe_image(target)
    assert "not found" in result


@pytest.mark.asyncio()
async def test_describe_image_unsupported_type(mock_env):
    """Return error for non-image file types."""
    tmp_path = mock_env
    (tmp_path / "doc.pdf").write_bytes(b"fake pdf")
    target = str(tmp_path / "doc.pdf")
    result = await describe_image(target)
    assert "Unsupported" in result


@pytest.mark.asyncio()
async def test_describe_image_success(mock_env):
    """Verify a successful vision model call returns the response text."""
    tmp_path = mock_env
    (tmp_path / "test.png").write_bytes(b"fake png data")
    target = str(tmp_path / "test.png")

    with patch("sdk.providers.vision_generate", _fake_vision_generate):
        result = await describe_image(target, "What is in this image?")
        assert result == "A test image showing a cat."
