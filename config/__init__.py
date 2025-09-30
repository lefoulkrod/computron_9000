"""Configuration loading utilities."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """Application settings."""

    home_dir: str
    default_model: str

    @field_validator("home_dir")
    @classmethod
    def validate_home_dir(cls, v: str) -> str:
        """Ensure home directory path is expanded."""
        return str(Path(v).expanduser())


class ModelConfig(BaseModel):
    """Configuration for a single model."""

    name: str
    model: str
    # Make options optional in YAML (missing or null) and normalize to an empty dict
    options: dict[str, Any] = Field(default_factory=dict)
    think: bool = False

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v: object) -> dict[str, Any]:
        """Normalize ``options`` allowing missing or null values.

        Args:
            v: Incoming value from YAML (may be None, dict, or missing).

        Returns:
            A dictionary of options (empty if unspecified).
        """
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        msg = "options must be a mapping if provided"
        raise TypeError(msg)


class SearchGoogleConfig(BaseModel):
    """Settings for Google search tool."""

    state_file: str = "./browser-state.json"
    no_save_state: bool = False
    timeout: int = 6000
    api_endpoint: str = "https://www.googleapis.com/customsearch/v1"
    search_engine_id: str | None = Field(
        default_factory=lambda: os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
    )


class HumanTypingConfig(BaseModel):
    """Typing simulation configuration."""

    delay_min_ms: int = 40
    delay_max_ms: int = 120
    extra_pause_every_chars: int = 6
    extra_pause_min_ms: int = 150
    extra_pause_max_ms: int = 300


class HumanPointerConfig(BaseModel):
    """Pointer movement simulation configuration."""

    move_steps: int = 10
    offset_px: float = 3.0
    hover_min_ms: int = 80
    hover_max_ms: int = 160
    click_hold_min_ms: int = 25
    click_hold_max_ms: int = 60


class BrowserHumanConfig(BaseModel):
    """Configuration for human-like browser interactions."""

    pointer: HumanPointerConfig = Field(default_factory=HumanPointerConfig)
    typing: HumanTypingConfig = Field(default_factory=HumanTypingConfig)


class BrowserToolsConfig(BaseModel):
    """Settings for browser tools."""

    human: BrowserHumanConfig = Field(default_factory=BrowserHumanConfig)
    waits: "BrowserWaitConfig" = Field(default_factory=lambda: BrowserWaitConfig())


class BrowserWaitConfig(BaseModel):
    """Configuration controlling browser wait/settle timeouts."""

    # Maximum time to wait for a navigation to begin/complete (ms)
    navigation_timeout_ms: int = 8000
    # When a navigation is detected, wait up to this many ms for network idle
    post_navigation_idle_timeout_ms: int = 6000
    # Cap for DOM mutation observer before giving up (ms)
    dom_mutation_timeout_ms: int = 1500
    # Window of quiet DOM mutations required before settling (ms)
    dom_quiet_window_ms: int = 200


# Note: BrowserWaitConfig is referenced as a forward-ref above to avoid
# reordering issues; Pydantic will resolve it when models are used.


class WebToolsConfig(BaseModel):
    """Settings for web tools."""

    search_google: SearchGoogleConfig = Field(default_factory=SearchGoogleConfig)


class ToolsConfig(BaseModel):
    """Settings for tools."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    browser: BrowserToolsConfig = Field(default_factory=BrowserToolsConfig)


class AgentConfig(BaseModel):
    """Settings for an individual agent."""

    think: bool = False


class AgentsConfig(BaseModel):
    """Settings for all agents."""

    web: AgentConfig = Field(default_factory=AgentConfig)
    file_system: AgentConfig = Field(default_factory=AgentConfig)


class RedditConfig(BaseModel):
    """Reddit API configuration."""

    client_id: str = Field(default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""))
    client_secret: str = Field(
        default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", ""),
    )
    user_agent: str = Field(default_factory=lambda: os.getenv("REDDIT_USER_AGENT", ""))


class VirtualComputerConfig(BaseModel):
    """Configuration for the virtual computer environment."""

    container_name: str
    container_user: str
    home_dir: str
    container_working_dir: str


class LLMConfig(BaseModel):
    """Configuration for Large Language Model connection."""

    host: str | None = None


class AppConfig(BaseModel):
    """Application level configuration."""

    models: list[ModelConfig]
    settings: Settings
    virtual_computer: VirtualComputerConfig
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @field_validator("models")
    @classmethod
    def validate_models_not_empty(cls, v: list[ModelConfig]) -> list[ModelConfig]:
        """Ensure at least one model is configured."""
        if not v:
            msg = "At least one model must be configured"
            raise ValueError(msg)
        return v

    def get_model_by_name(self, name: str) -> ModelConfig | None:
        """Get a model configuration by name.

        Args:
            name: The model name to search for.

        Returns:
            The model configuration if found, None otherwise.

        """
        return next((model for model in self.models if model.name == name), None)

    def get_default_model(self) -> ModelConfig:
        """Get the default model configuration.

        Returns:
            The default model configuration.

        Raises:
            ValueError: If the default model is not found.

        """
        model = self.get_model_by_name(self.settings.default_model)
        if model is None:
            msg = f"Default model '{self.settings.default_model}' not found in configured models"
            raise ValueError(msg)
        return model


logger = logging.getLogger(__name__)

# Ensure environment variables from a local .env file are available as early as possible
# so that env-driven defaults (e.g., LLM_HOST) are read correctly even when configuration
# is loaded during import time in other modules.
load_dotenv()


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load application configuration from ``config.yaml``.

    Returns:
        AppConfig: Parsed configuration dataclass.

    Raises:
        RuntimeError: If the configuration file cannot be read or parsed.

    """
    path = Path(__file__).parent.parent / "config.yaml"
    logger.info("Loading configuration from %s", path)

    try:
        with path.open(encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)

        # Convert models to list of ModelConfig if present
        if "models" in data:
            data["models"] = [ModelConfig(**m) for m in data["models"]]

        config = AppConfig(**data)
        # Apply environment variable precedence: if LLM_HOST is set and non-blank,
        # override any YAML-provided llm.host value.
        env_host = os.getenv("LLM_HOST")
        if env_host is not None and env_host.strip() != "":
            config.llm.host = env_host
        logger.info(
            "Successfully loaded configuration with %d models",
            len(config.models),
        )

    except FileNotFoundError as exc:
        msg = f"Config file not found: {path}"
        logger.exception(msg)
        raise RuntimeError(msg) from exc
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in config file {path}: {exc}"
        logger.exception(msg)
        raise RuntimeError(msg) from exc
    except Exception as exc:
        msg = f"Failed to load config from {path}: {exc}"
        logger.exception(msg)
        raise RuntimeError(msg) from exc
    else:
        return config
