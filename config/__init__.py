"""Configuration loading utilities."""

from pydantic import BaseModel
import yaml
from pathlib import Path
from functools import lru_cache

class LlmConfig(BaseModel):
    """Settings for the language model."""

    model: str

class AppConfig(BaseModel):
    """Application level configuration."""

    llm: LlmConfig

@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load application configuration from ``config.yaml``.

    Returns:
        AppConfig: Parsed configuration dataclass.

    Raises:
        RuntimeError: If the configuration file cannot be read or parsed.
    """

    path = Path(__file__).parent.parent / "config.yaml"
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {path}") from exc
    except Exception as e:
        raise RuntimeError(f"Failed to load config: {e}") from e
