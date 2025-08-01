"""
Tests for the models module.
"""

from unittest.mock import MagicMock, patch

import pytest

from config import ModelConfig, Settings
from models import ModelNotFoundError, get_default_model, get_model_by_name


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return MagicMock(
        models=[
            ModelConfig(name="gemma3", model="gemma:3b", options={}),
            ModelConfig(name="llama", model="llama:7b", options={}),
        ],
        settings=Settings(default_model="gemma3", home_dir="not/used"),
    )


@pytest.mark.unit
@patch("models.model_configs.load_config")
def test_get_default_model(mock_load_config, mock_config):
    """Test retrieving the default model configuration."""
    mock_load_config.return_value = mock_config
    model = get_default_model()
    assert model.name == "gemma3"
    assert model.model == "gemma:3b"


@pytest.mark.unit
@patch("models.model_configs.load_config")
def test_get_model_by_name(mock_load_config, mock_config):
    """Test retrieving a model configuration by name."""
    mock_load_config.return_value = mock_config
    model = get_model_by_name("llama")
    assert model.name == "llama"
    assert model.model == "llama:7b"


@pytest.mark.unit
@patch("models.model_configs.load_config")
def test_get_model_by_name_not_found(mock_load_config, mock_config):
    """Test that ModelNotFoundError is raised when a model is not found."""
    mock_load_config.return_value = mock_config
    with pytest.raises(ModelNotFoundError):
        get_model_by_name("nonexistent_model")
