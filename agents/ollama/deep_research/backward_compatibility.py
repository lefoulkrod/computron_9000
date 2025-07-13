"""
Backward compatibility layer for the Deep Research Agent.

This module maintains the original single-agent interface while internally
using the new multi-agent infrastructure when appropriate.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.ollama.deep_research.shared import (
    AgentSourceTracker,
    SharedSourceRegistry,
    get_agent_config,
)
from agents.ollama.deep_research.source_tracker import SourceTracker
from agents.ollama.deep_research.tracked_tools import (
    get_tracked_reddit_tools,
    get_tracked_web_tools,
)

logger = logging.getLogger(__name__)


class BackwardCompatibilitySourceTracker:
    """
    Wrapper that provides backward compatibility for the original SourceTracker interface
    while using the new agent-specific source tracking infrastructure.
    """

    def __init__(self) -> None:
        """Initialize backward compatibility source tracker."""
        # Create a shared registry for legacy usage
        self._shared_registry = SharedSourceRegistry()
        
        # Create an agent tracker for the legacy single-agent
        self._agent_tracker = AgentSourceTracker(
            agent_id="legacy_deep_research",
            shared_registry=self._shared_registry
        )
        
        logger.info("Initialized backward compatibility source tracker")

    def register_access(
        self, url: str, tool_name: str, query: Optional[str] = None
    ) -> None:
        """
        Register a source access (backward compatible interface).

        Args:
            url (str): The URL of the source accessed.
            tool_name (str): The name of the tool used to access the source.
            query (Optional[str]): The query or parameters used, if applicable.
        """
        self._agent_tracker.register_access(url, tool_name, query)

    def register_source(self, source: Any) -> None:
        """
        Register a source (backward compatible interface).

        Args:
            source: The source to register.
        """
        self._agent_tracker.register_source(source)

    def get_source(self, url: str) -> Optional[Any]:
        """
        Get a source by URL (backward compatible interface).

        Args:
            url (str): The URL of the source.

        Returns:
            Optional[Any]: The source if found, None otherwise.
        """
        return self._agent_tracker.get_source(url)

    def get_all_sources(self) -> List[Any]:
        """Get all sources (backward compatible interface)."""
        return self._agent_tracker.get_local_sources()

    def get_citations(self) -> List[Any]:
        """Get citations (backward compatible interface)."""
        return self._agent_tracker.get_citations()

    def get_source_summary(self) -> Dict[str, int]:
        """Get source summary (backward compatible interface)."""
        accesses = self._agent_tracker.get_local_accesses()
        sources = self._agent_tracker.get_local_sources()
        
        return {
            "total_sources": len(sources),
            "total_accesses": len(accesses),
            "unique_urls": len({access.url for access in accesses}),
        }

    # Additional methods for compatibility with original SourceTracker
    def clear(self) -> None:
        """Clear tracking data."""
        self._agent_tracker.clear_local_data()

    def has_accessed(self, url: str) -> bool:
        """Check if URL has been accessed."""
        return self._agent_tracker.has_accessed(url)


class LegacyAgentConfig:
    """
    Provides backward compatibility for legacy agent configuration usage.
    """

    def __init__(self) -> None:
        """Initialize legacy agent config."""
        # Use the coordinator config as default for legacy usage
        self._config = get_agent_config("coordinator")

    @property
    def model(self) -> str:
        """Get model name."""
        model, _ = self._config.get_model_settings()
        return model

    @property
    def options(self) -> Dict[str, Any]:
        """Get model options."""
        _, options = self._config.get_model_settings()
        return options


def create_legacy_source_tracker() -> BackwardCompatibilitySourceTracker:
    """
    Create a source tracker that provides backward compatibility.

    Returns:
        BackwardCompatibilitySourceTracker: A backward compatible source tracker.
    """
    return BackwardCompatibilitySourceTracker()


def get_legacy_tracked_tools(source_tracker: BackwardCompatibilitySourceTracker) -> Dict[str, Any]:
    """
    Get tracked tools with legacy interface compatibility.

    Args:
        source_tracker (BackwardCompatibilitySourceTracker): The source tracker to use.

    Returns:
        Dict[str, Any]: Dictionary of tracked tool functions.
    """
    # Create a compatibility layer that wraps the agent tracker
    legacy_tracker = SourceTracker()
    
    # Copy methods from the backward compatibility tracker
    legacy_tracker.register_access = source_tracker.register_access
    legacy_tracker.register_source = source_tracker.register_source
    legacy_tracker.get_source = source_tracker.get_source
    
    # Get the original tracked tools
    web_tools = get_tracked_web_tools(legacy_tracker)
    reddit_tools = get_tracked_reddit_tools(legacy_tracker)
    
    # Combine and return
    all_tools = {}
    all_tools.update(web_tools)
    all_tools.update(reddit_tools)
    
    return all_tools


# Module exports
__all__ = [
    "BackwardCompatibilitySourceTracker",
    "LegacyAgentConfig",
    "create_legacy_source_tracker",
    "get_legacy_tracked_tools",
]
