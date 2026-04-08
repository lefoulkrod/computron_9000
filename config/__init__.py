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

    @field_validator("home_dir")
    @classmethod
    def validate_home_dir(cls, v: str) -> str:
        """Ensure home directory path is expanded."""
        return str(Path(v).expanduser())


class _ModelOptions(BaseModel):
    """Shared base for config sections that specify a model with options."""

    model: str
    options: dict[str, Any] = Field(default_factory=dict)
    think: bool = False

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v: object) -> dict[str, Any]:
        """Normalize ``options`` allowing missing or null values."""
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        msg = "options must be a mapping if provided"
        raise TypeError(msg)


class VisionConfig(_ModelOptions):
    """Configuration for the vision model used by browser and virtual computer tools."""


class SummaryConfig(_ModelOptions):
    """Configuration for the summarization model used for context compaction."""


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

    channel: str | None = None  # None = bundled Chromium, "chrome" = system Chrome
    headless: bool = False  # False = visible window, True = no GUI
    human: BrowserHumanConfig = Field(default_factory=BrowserHumanConfig)
    waits: "BrowserWaitConfig" = Field(default_factory=lambda: BrowserWaitConfig())
    scroll_warn_threshold: int = 5
    scroll_hard_limit: int = 10


class BrowserWaitConfig(BaseModel):
    """Configuration controlling browser wait/settle timeouts."""

    network_idle_timeout_ms: int = 3000
    font_timeout_ms: int = 1000
    dom_mutation_timeout_ms: int = 1500
    dom_quiet_window_ms: int = 150
    animation_timeout_ms: int = 1000


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


class DesktopConfig(BaseModel):
    """Configuration for the desktop environment (noVNC + Xfce4)."""

    display: str = ":1"
    user_display: str = ":99"
    agent_display_base: int = 100
    resolution: str = "1280x720"
    vnc_port: int = 5900
    websocket_port: int = 6080
    screenshot_quality: int = 70
    vision_model: str | None = "qwen3.5:4b"


class VirtualComputerConfig(BaseModel):
    """Configuration for the virtual computer environment."""

    container_name: str
    container_user: str
    home_dir: str
    container_working_dir: str


class InferenceContainerConfig(BaseModel):
    """Configuration for the GPU inference container."""

    container_name: str
    home_dir: str
    container_working_dir: str


class LLMConfig(BaseModel):
    """Configuration for Large Language Model connection."""

    provider: str = "ollama"
    host: str | None = None
    api_key: str | None = Field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    base_url: str | None = None


class SkillsConfig(BaseModel):
    """Configuration for the skills learning system."""

    enabled: bool = True
    extraction_interval_seconds: int = 300
    extraction_model: str = "qwen3:8b"
    extraction_options: dict[str, Any] = Field(
        default_factory=lambda: {"num_ctx": 60000},
    )
    max_skills: int = 200
    single_conversation_extraction: bool = True


class ParallelConfig(BaseModel):
    """Configuration for parallel agent execution."""

    enabled: bool = False
    max_concurrent: int = 4


class NotificationsConfig(BaseModel):
    """Telegram push notification settings for goal run completion/failure."""

    enabled: bool = False
    on_run_completed: bool = True
    on_run_failed: bool = True
    include_files: bool = True
    max_attachment_size_mb: int = 50


class GoalsConfig(BaseModel):
    """Configuration for the autonomous task engine."""

    enabled: bool = True
    goals_dir: str = ""  # empty = ~/.computron_9000/goals/
    poll_interval: int = 5
    max_concurrent: int = 2
    max_retries: int = 3
    shutdown_timeout: int = 60
    timezone: str = "UTC"  # Default timezone for goals (IANA name)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    # LLM options for task execution
    model: str = ""  # empty = use server default
    num_ctx: int = 0  # 0 = use model default
    think: bool = False
    max_iterations: int = 0


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""

    name: str
    command: str  # Command to start the server (e.g., "npx", "python", "docker")
    args: list[str] = Field(default_factory=list)  # Arguments for the command
    env: dict[str, str] = Field(default_factory=dict)  # Environment variables
    timeout: int = 30  # Connection timeout in seconds
    enabled: bool = True


class MCPConfig(BaseModel):
    """Configuration for MCP client integration."""

    enabled: bool = False
    servers: list[MCPServerConfig] = Field(default_factory=list)
    auto_discover: bool = False  # Auto-discover local MCP servers
    tool_prefix: str = "mcp_"  # Prefix for MCP tool names


class AppConfig(BaseModel):
    """Application level configuration."""

    settings: Settings
    virtual_computer: VirtualComputerConfig
    inference_container: InferenceContainerConfig
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    vision: VisionConfig | None = None
    summary: SummaryConfig | None = None
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)
    goals: GoalsConfig = Field(default_factory=GoalsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


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

        config = AppConfig(**data)
        # Apply environment variable precedence: if LLM_HOST is set and non-blank,
        # override any YAML-provided llm.host value.
        env_host = os.getenv("LLM_HOST")
        if env_host is not None and env_host.strip() != "":
            config.llm.host = env_host
        logger.info("Successfully loaded configuration")

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
