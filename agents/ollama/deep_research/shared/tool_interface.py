"""
Unified tool interface patterns for multi-agent compatibility.

This module provides base classes and patterns for creating agent-specific
tools that can work together in the multi-agent system.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker

logger = logging.getLogger(__name__)


class ToolResult(Protocol):
    """Protocol for tool results that can be passed between agents."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        ...

    def get_summary(self) -> str:
        """Get a brief summary of the result."""
        ...


class AgentTool(ABC):
    """
    Base class for agent-specific tools.
    
    Provides common functionality for source tracking, error handling,
    and result formatting that all agent tools should have.
    """

    def __init__(
        self,
        tool_name: str,
        agent_id: str,
        source_tracker: Optional[AgentSourceTracker] = None
    ) -> None:
        """
        Initialize agent tool.

        Args:
            tool_name (str): Name of the tool.
            agent_id (str): ID of the agent using this tool.
            source_tracker (Optional[AgentSourceTracker]): Source tracker for this agent.
        """
        self.tool_name = tool_name
        self.agent_id = agent_id
        self.source_tracker = source_tracker
        self.logger = logging.getLogger(f"{__name__}.{agent_id}.{tool_name}")

    def track_source_access(
        self,
        url: str,
        query: Optional[str] = None
    ) -> None:
        """
        Track access to a source if source tracker is available.

        Args:
            url (str): URL of the source accessed.
            query (Optional[str]): Query used to access the source.
        """
        if self.source_tracker:
            self.source_tracker.register_access(
                url=url,
                tool_name=self.tool_name,
                query=query
            )
            self.logger.debug(f"Tracked source access: {url}")

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            Any: Tool-specific result.
        """
        pass

    def get_tool_info(self) -> Dict[str, str]:
        """Get information about this tool."""
        return {
            "name": self.tool_name,
            "agent_id": self.agent_id,
            "type": self.__class__.__name__,
        }


class WebResearchTool(AgentTool):
    """Base class for web research tools."""

    def __init__(
        self,
        tool_name: str,
        agent_id: str = "web_research",
        source_tracker: Optional[AgentSourceTracker] = None
    ) -> None:
        super().__init__(tool_name, agent_id, source_tracker)


class SocialResearchTool(AgentTool):
    """Base class for social research tools."""

    def __init__(
        self,
        tool_name: str,
        agent_id: str = "social_research",
        source_tracker: Optional[AgentSourceTracker] = None
    ) -> None:
        super().__init__(tool_name, agent_id, source_tracker)


class AnalysisTool(AgentTool):
    """Base class for analysis tools."""

    def __init__(
        self,
        tool_name: str,
        agent_id: str = "analysis",
        source_tracker: Optional[AgentSourceTracker] = None
    ) -> None:
        super().__init__(tool_name, agent_id, source_tracker)


class SynthesisTool(AgentTool):
    """Base class for synthesis tools."""

    def __init__(
        self,
        tool_name: str,
        agent_id: str = "synthesis",
        source_tracker: Optional[AgentSourceTracker] = None
    ) -> None:
        super().__init__(tool_name, agent_id, source_tracker)


class ToolRegistry:
    """
    Registry for managing agent-specific tools.
    
    Allows agents to register their tools and enables cross-agent
    tool discovery and usage patterns.
    """

    def __init__(self) -> None:
        """Initialize empty tool registry."""
        self._tools: Dict[str, Dict[str, AgentTool]] = {}  # agent_id -> tool_name -> tool

    def register_tool(self, agent_id: str, tool: AgentTool) -> None:
        """
        Register a tool for a specific agent.

        Args:
            agent_id (str): ID of the agent.
            tool (AgentTool): The tool to register.
        """
        if agent_id not in self._tools:
            self._tools[agent_id] = {}
        
        self._tools[agent_id][tool.tool_name] = tool
        logger.info(f"Registered tool {tool.tool_name} for agent {agent_id}")

    def get_tool(self, agent_id: str, tool_name: str) -> Optional[AgentTool]:
        """
        Get a specific tool for an agent.

        Args:
            agent_id (str): ID of the agent.
            tool_name (str): Name of the tool.

        Returns:
            Optional[AgentTool]: The tool if found, None otherwise.
        """
        return self._tools.get(agent_id, {}).get(tool_name)

    def get_agent_tools(self, agent_id: str) -> Dict[str, AgentTool]:
        """
        Get all tools for a specific agent.

        Args:
            agent_id (str): ID of the agent.

        Returns:
            Dict[str, AgentTool]: Dictionary of tool_name -> tool.
        """
        return self._tools.get(agent_id, {}).copy()

    def get_all_agents(self) -> List[str]:
        """Get list of all agents with registered tools."""
        return list(self._tools.keys())

    def get_tool_list(self, agent_id: str) -> List[str]:
        """Get list of tool names for a specific agent."""
        return list(self._tools.get(agent_id, {}).keys())


class StandardErrorHandling:
    """
    Standard error handling patterns for agent tools.
    
    Provides consistent error handling, logging, and recovery
    patterns across all agent tools.
    """

    @staticmethod
    def handle_network_error(error: Exception, url: str, tool_name: str) -> Dict[str, Any]:
        """
        Handle network-related errors consistently.

        Args:
            error (Exception): The network error.
            url (str): URL that caused the error.
            tool_name (str): Name of the tool that encountered the error.

        Returns:
            Dict[str, Any]: Standardized error response.
        """
        logger.error(f"Network error in {tool_name} for {url}: {error}")
        return {
            "success": False,
            "error_type": "network_error",
            "error_message": str(error),
            "url": url,
            "tool_name": tool_name,
        }

    @staticmethod
    def handle_parsing_error(error: Exception, content: str, tool_name: str) -> Dict[str, Any]:
        """
        Handle content parsing errors consistently.

        Args:
            error (Exception): The parsing error.
            content (str): Content that failed to parse.
            tool_name (str): Name of the tool that encountered the error.

        Returns:
            Dict[str, Any]: Standardized error response.
        """
        logger.error(f"Parsing error in {tool_name}: {error}")
        return {
            "success": False,
            "error_type": "parsing_error",
            "error_message": str(error),
            "content_length": len(content),
            "tool_name": tool_name,
        }

    @staticmethod
    def handle_validation_error(error: Exception, input_data: Any, tool_name: str) -> Dict[str, Any]:
        """
        Handle input validation errors consistently.

        Args:
            error (Exception): The validation error.
            input_data (Any): Input data that failed validation.
            tool_name (str): Name of the tool that encountered the error.

        Returns:
            Dict[str, Any]: Standardized error response.
        """
        logger.error(f"Validation error in {tool_name}: {error}")
        return {
            "success": False,
            "error_type": "validation_error",
            "error_message": str(error),
            "input_data_type": type(input_data).__name__,
            "tool_name": tool_name,
        }


# Global tool registry instance
_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _tool_registry


def register_agent_tool(agent_id: str, tool: AgentTool) -> None:
    """
    Register a tool for a specific agent in the global registry.

    Args:
        agent_id (str): ID of the agent.
        tool (AgentTool): The tool to register.
    """
    _tool_registry.register_tool(agent_id, tool)


# Module exports
__all__ = [
    "ToolResult",
    "AgentTool",
    "WebResearchTool",
    "SocialResearchTool",
    "AnalysisTool",
    "SynthesisTool",
    "ToolRegistry",
    "StandardErrorHandling",
    "get_tool_registry",
    "register_agent_tool",
]
