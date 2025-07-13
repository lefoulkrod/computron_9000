"""
Model configuration management utilities.
"""

import logging

from config import ModelConfig, load_config

logger = logging.getLogger(__name__)
config = load_config()


class ModelNotFoundError(Exception):
    """
    Exception raised when a model configuration is not found by name.
    """

    pass


def get_default_model() -> ModelConfig:
    """
    Retrieve the default model configuration.

    Returns:
        ModelConfig: The default model configuration.
    """
    default_model = config.settings.default_model
    return get_model_by_name(default_model)


def get_model_by_name(name: str) -> ModelConfig:
    """
    Retrieve a model configuration by name.

    Args:
        name (str): The name of the model to retrieve.

    Returns:
        ModelConfig: The model config if found.

    Raises:
        ModelNotFoundError: If the model with the given name is not found.
    """
    config = load_config()
    for model in config.models:
        if model.name == name:
            return model
    logger.error(f"Model with name '{name}' not found.")
    raise ModelNotFoundError(f"Model with name '{name}' not found.")
