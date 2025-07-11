"""Configuration loading utilities."""

from pydantic import BaseModel, Field
import yaml
from pathlib import Path
from functools import lru_cache
import os

class Settings(BaseModel):
    """Application settings."""

    home_dir: str = "/home/larry/.computron_9000"


class ModelConfig(BaseModel):
    """Configuration for a single model."""
    name: str
    model: str
    options: dict



class AdkConfig(BaseModel):
    """Settings for ADK agents."""

    provider: str


class SearchGoogleConfig(BaseModel):
    """Settings for Google search tool."""
    
    state_file: str = "./browser-state.json"
    no_save_state: bool = False
    timeout: int = 6000


class WebToolsConfig(BaseModel):
    """Settings for web tools."""
    
    search_google: SearchGoogleConfig = SearchGoogleConfig()


class ToolsConfig(BaseModel):
    """Settings for tools."""
    
    web: WebToolsConfig = WebToolsConfig()


class AgentConfig(BaseModel):
    """Settings for an individual agent."""
    think: bool = False


class AgentsConfig(BaseModel):
    """Settings for all agents."""
    web: AgentConfig = AgentConfig()
    file_system: AgentConfig = AgentConfig()


class RedditConfig(BaseModel):
    """Reddit API configuration."""
    client_id: str = Field(default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""))
    client_secret: str = Field(default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", ""))
    user_agent: str = Field(default_factory=lambda: os.getenv("REDDIT_USER_AGENT", ""))




class AppConfig(BaseModel):
    """Application level configuration."""
    models: list[ModelConfig]
    adk: AdkConfig
    tools: ToolsConfig = ToolsConfig()
    settings: Settings = Settings()
    agents: AgentsConfig = AgentsConfig()
    reddit: RedditConfig = RedditConfig()

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
        # Convert models to list of ModelConfig if present
        if "models" in data:
            data["models"] = [ModelConfig(**m) for m in data["models"]]
        return AppConfig(**data)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {path}") from exc
    except Exception as e:
        raise RuntimeError(f"Failed to load config: {e}") from e
