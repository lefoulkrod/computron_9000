"""
Agent-specific configuration management for the Deep Research multi-agent system.

This module provides configuration management that allows each agent to have
specialized settings while maintaining sensible defaults.
"""

import logging
from typing import Any

from models import get_model_by_name

logger = logging.getLogger(__name__)


class AgentConfig:
    """
    Configuration container for a specific agent.

    Provides agent-specific model settings, parameters, and options
    while falling back to shared defaults.
    """

    def __init__(
        self,
        agent_type: str,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        custom_options: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize agent configuration.

        Args:
            agent_type (str): Type of agent (e.g., 'web_research', 'social_research')
            model_name (Optional[str]): Specific model to use, defaults to 'deep_research'
            temperature (Optional[float]): Temperature override for this agent
            max_tokens (Optional[int]): Max tokens override for this agent
            custom_options (Optional[Dict[str, Any]]): Additional model options
        """
        self.agent_type = agent_type
        self.model_name = model_name or "research_coordinator"

        # Load base configuration
        base_model = get_model_by_name(self.model_name)

        # Apply agent-specific overrides
        self.model = base_model.model
        self.options = base_model.options.copy() if base_model.options else {}

        # Override with agent-specific settings
        if temperature is not None:
            self.options["temperature"] = temperature
        if max_tokens is not None:
            self.options["max_tokens"] = max_tokens
        if custom_options:
            self.options.update(custom_options)

        logger.info(f"Configured agent {agent_type} with model {self.model_name}")

    def get_model_settings(self) -> tuple[str, dict[str, Any]]:
        """
        Get model and options for agent initialization.

        Returns:
            tuple[str, Dict[str, Any]]: (model_name, options)
        """
        return self.model, self.options


class MultiAgentConfigManager:
    """
    Manages configurations for all agents in the multi-agent system.

    Provides centralized configuration with agent-specific customizations.
    """

    # Default configurations for each agent type
    DEFAULT_AGENT_CONFIGS: dict[str, dict[str, Any]] = {
        "coordinator": {
            "model_name": "research_coordinator",  # Use dedicated coordinator model
            "temperature": 0.3,  # Lower temperature for coordination decisions
            "max_tokens": 4000,
        },
        "query_decomposition": {
            "temperature": 0.2,  # Very focused for query analysis
            "max_tokens": 2000,
        },
        "web_research": {
            "temperature": 0.4,  # Balanced for web research
            "max_tokens": 6000,
        },
        "social_research": {
            "temperature": 0.5,  # Higher for social analysis
            "max_tokens": 6000,
        },
        "analysis": {
            "temperature": 0.2,  # Focused for analysis
            "max_tokens": 5000,
        },
        "synthesis": {
            "temperature": 0.3,  # Balanced for synthesis
            "max_tokens": 8000,
        },
    }

    def __init__(self) -> None:
        """Initialize the multi-agent configuration manager."""
        self._agent_configs: dict[str, AgentConfig] = {}
        self._initialize_default_configs()

    def _initialize_default_configs(self) -> None:
        """Initialize default configurations for all agent types."""
        for agent_type, config_overrides in self.DEFAULT_AGENT_CONFIGS.items():
            temperature = config_overrides.get("temperature")
            max_tokens = config_overrides.get("max_tokens")

            self._agent_configs[agent_type] = AgentConfig(
                agent_type=agent_type,
                temperature=temperature,
                max_tokens=int(max_tokens) if max_tokens is not None else None,
                custom_options=None,  # No custom options in default configs
            )

    def get_agent_config(self, agent_type: str) -> AgentConfig:
        """
        Get configuration for a specific agent type.

        Args:
            agent_type (str): The type of agent to get config for.

        Returns:
            AgentConfig: The agent configuration.

        Raises:
            ValueError: If agent type is not recognized.
        """
        if agent_type not in self._agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return self._agent_configs[agent_type]

    def register_agent_config(self, agent_type: str, config: AgentConfig) -> None:
        """
        Register a custom configuration for an agent type.

        Args:
            agent_type (str): The agent type to configure.
            config (AgentConfig): The configuration to register.
        """
        self._agent_configs[agent_type] = config
        logger.info(f"Registered custom config for agent type: {agent_type}")

    def get_all_agent_types(self) -> list[str]:
        """Get list of all configured agent types."""
        return list(self._agent_configs.keys())


# Global configuration manager instance
_config_manager = MultiAgentConfigManager()


def get_agent_config(agent_type: str) -> AgentConfig:
    """
    Get configuration for a specific agent type.

    Args:
        agent_type (str): The type of agent to get config for.

    Returns:
        AgentConfig: The agent configuration.
    """
    return _config_manager.get_agent_config(agent_type)


def register_custom_agent_config(
    agent_type: str,
    model_name: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    custom_options: dict[str, Any] | None = None,
) -> None:
    """
    Register a custom configuration for an agent type.

    Args:
        agent_type (str): The agent type to configure.
        model_name (Optional[str]): Specific model to use.
        temperature (Optional[float]): Temperature override.
        max_tokens (Optional[int]): Max tokens override.
        custom_options (Optional[Dict[str, Any]]): Additional options.
    """
    config = AgentConfig(
        agent_type=agent_type,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        custom_options=custom_options,
    )
    _config_manager.register_agent_config(agent_type, config)


# Module exports
__all__ = [
    "AgentConfig",
    "MultiAgentConfigManager",
    "get_agent_config",
    "register_custom_agent_config",
]
