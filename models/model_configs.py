"""Model configuration management utilities."""

import logging

from config import ModelConfig, load_config

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """Exception raised when a model configuration is not found by name."""

    def __init__(self, name: str) -> None:
        """Initialize ModelNotFoundError with the missing model name.

        Args:
            name (str): The name of the model that was not found.
        """
        msg: str = f"Model with name '{name}' not found."
        super().__init__(msg)


def get_default_model() -> ModelConfig:
    """Return the default model configuration."""
    config = load_config()
    default_model = config.settings.default_model
    return get_model_by_name(default_model)


def get_think_for_model_str(model_str: str) -> bool | None:
    """Return the think flag for the first config entry whose model string matches.

    Args:
        model_str (str): The model identifier string (e.g. ``glm-4.7-flash:q8_0``).

    Returns:
        bool | None: The think value, or None if no matching config is found.
    """
    config = load_config()
    for model_cfg in config.models:
        if model_cfg.model == model_str:
            return model_cfg.think
    return None


def get_model_by_name(name: str) -> ModelConfig:
    """Return a model configuration by name.

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
    logger.exception("Model with name '%s' not found.", name)
    raise ModelNotFoundError(name)
