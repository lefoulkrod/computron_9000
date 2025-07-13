"""
Shared source tracking infrastructure for multi-agent research system.

This module provides agent-specific source trackers and a shared source registry
to avoid conflicts between agents while enabling source deduplication.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any

import pydantic

from agents.ollama.deep_research.types import ResearchCitation, ResearchSource

logger = logging.getLogger(__name__)


class SourceAccess(pydantic.BaseModel):
    """
    Represents an access to a source during research.

    Attributes:
        url (str): The URL of the source.
        tool_name (str): The name of the tool used to access the source.
        timestamp (float): Unix timestamp of when the source was accessed.
        query (Optional[str]): The query or parameters used to access the source, if applicable.
        agent_id (str): Identifier of the agent that accessed the source.
    """

    url: str
    tool_name: str
    timestamp: float
    agent_id: str
    query: str | None = None

    @property
    def access_datetime(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.timestamp)

    @property
    def formatted_access_time(self) -> str:
        """Return formatted access time string."""
        return self.access_datetime.strftime("%Y-%m-%d %H:%M:%S")


class SharedSourceRegistry:
    """
    Shared registry for deduplicating sources across agents.

    This registry maintains a global view of all sources accessed during
    a research workflow to avoid duplicate processing and enable
    cross-reference verification.
    """

    def __init__(self) -> None:
        """Initialize an empty shared source registry."""
        self._sources: dict[str, ResearchSource] = {}  # url -> ResearchSource
        self._all_accesses: list[SourceAccess] = []  # All source accesses across agents
        self._agent_accesses: dict[str, list[SourceAccess]] = {}  # agent_id -> accesses

    def register_source(self, source: ResearchSource) -> None:
        """
        Register a source in the shared registry.

        Args:
            source (ResearchSource): The source to register.
        """
        self._sources[source.url] = source
        logger.info(f"Registered shared source: {source.title} ({source.url})")

    def get_source(self, url: str) -> ResearchSource | None:
        """
        Get a source from the shared registry.

        Args:
            url (str): The URL of the source.

        Returns:
            Optional[ResearchSource]: The source if found, None otherwise.
        """
        return self._sources.get(url)

    def has_source(self, url: str) -> bool:
        """
        Check if a source is already in the registry.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if source exists in registry.
        """
        return url in self._sources

    def register_access(self, access: SourceAccess) -> None:
        """
        Register a source access in the shared registry.

        Args:
            access (SourceAccess): The source access to register.
        """
        self._all_accesses.append(access)

        if access.agent_id not in self._agent_accesses:
            self._agent_accesses[access.agent_id] = []
        self._agent_accesses[access.agent_id].append(access)

    def get_all_sources(self) -> list[ResearchSource]:
        """Get all sources in the registry."""
        return list(self._sources.values())

    def get_accesses_by_agent(self, agent_id: str) -> list[SourceAccess]:
        """Get all accesses by a specific agent."""
        return self._agent_accesses.get(agent_id, [])

    def get_all_accesses(self) -> list[SourceAccess]:
        """Get all source accesses across all agents."""
        return self._all_accesses

    def get_accessing_agents(self, url: str) -> set[str]:
        """Get set of agent IDs that have accessed a specific URL."""
        return {access.agent_id for access in self._all_accesses if access.url == url}

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the registry to a dictionary for persistence.

        Returns:
            dict: Serializable dictionary representation of the registry.
        """
        return {
            "sources": {url: source.model_dump() for url, source in self._sources.items()},
            "all_accesses": [access.model_dump() for access in self._all_accesses],
            "agent_accesses": {
                agent_id: [access.model_dump() for access in accesses]
                for agent_id, accesses in self._agent_accesses.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SharedSourceRegistry":
        """
        Restore the registry from a serialized dictionary.

        Args:
            data (dict): Dictionary representation from to_dict().

        Returns:
            SharedSourceRegistry: Restored registry instance.
        """
        registry = cls()

        # Restore sources
        for url, source_data in data.get("sources", {}).items():
            source = ResearchSource.model_validate(source_data)
            registry._sources[url] = source

        # Restore accesses
        for access_data in data.get("all_accesses", []):
            access = SourceAccess.model_validate(access_data)
            registry._all_accesses.append(access)

        # Restore agent accesses
        for agent_id, accesses_data in data.get("agent_accesses", {}).items():
            registry._agent_accesses[agent_id] = [
                SourceAccess.model_validate(access_data) for access_data in accesses_data
            ]

        return registry

    def to_json(self) -> str:
        """
        Serialize the registry to JSON string for persistence.

        Returns:
            str: JSON representation of the registry.
        """
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SharedSourceRegistry":
        """
        Restore the registry from a JSON string.

        Args:
            json_str (str): JSON string from to_json().

        Returns:
            SharedSourceRegistry: Restored registry instance.
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    def clear(self) -> None:
        """Clear all registry data."""
        self._sources.clear()
        self._all_accesses.clear()
        self._agent_accesses.clear()
        logger.info("Cleared shared source registry")


class AgentSourceTracker:
    """
    Agent-specific source tracker that works with the shared registry.

    Each agent gets its own tracker instance to avoid state conflicts,
    while the shared registry enables cross-agent source deduplication.
    """

    def __init__(self, agent_id: str, shared_registry: SharedSourceRegistry) -> None:
        """
        Initialize agent-specific source tracker.

        Args:
            agent_id (str): Unique identifier for this agent.
            shared_registry (SharedSourceRegistry): Shared registry for cross-agent coordination.
        """
        self.agent_id = agent_id
        self.shared_registry = shared_registry
        self._local_accesses: list[SourceAccess] = []  # This agent's accesses
        self._local_sources: dict[str, ResearchSource] = {}  # This agent's sources

    def register_access(
        self, url: str, tool_name: str, query: str | None = None
    ) -> None:
        """
        Register a source access with both local and shared tracking.

        Args:
            url (str): The URL of the source accessed.
            tool_name (str): The name of the tool used to access the source.
            query (Optional[str]): The query or parameters used, if applicable.
        """
        access = SourceAccess(
            url=url,
            tool_name=tool_name,
            timestamp=time.time(),
            agent_id=self.agent_id,
            query=query,
        )

        # Register locally
        self._local_accesses.append(access)

        # Register with shared registry
        self.shared_registry.register_access(access)

        logger.info(f"Agent {self.agent_id} accessed source: {url} via {tool_name}")

    def register_source(self, source: ResearchSource) -> None:
        """
        Register a source with both local and shared tracking.

        Args:
            source (ResearchSource): The source to register.
        """
        # Register locally
        self._local_sources[source.url] = source

        # Register with shared registry (only if not already there)
        if not self.shared_registry.has_source(source.url):
            self.shared_registry.register_source(source)

        logger.info(
            f"Agent {self.agent_id} registered source: {source.title} ({source.url})"
        )

    def get_source(self, url: str) -> ResearchSource | None:
        """
        Get a source, checking local cache first then shared registry.

        Args:
            url (str): The URL of the source.

        Returns:
            Optional[ResearchSource]: The source if found, None otherwise.
        """
        # Check local cache first
        if url in self._local_sources:
            return self._local_sources[url]

        # Check shared registry
        return self.shared_registry.get_source(url)

    def get_local_accesses(self) -> list[SourceAccess]:
        """Get all accesses made by this agent."""
        return self._local_accesses.copy()

    def get_local_sources(self) -> list[ResearchSource]:
        """Get all sources registered by this agent."""
        return list(self._local_sources.values())

    def has_accessed(self, url: str) -> bool:
        """Check if this agent has accessed a specific URL."""
        return any(access.url == url for access in self._local_accesses)

    def get_citations(self) -> list[ResearchCitation]:
        """
        Generate citations for all sources accessed by this agent.

        Returns:
            List[ResearchCitation]: List of citations for accessed sources.
        """
        citations = []

        # Get unique URLs accessed by this agent
        accessed_urls = {access.url for access in self._local_accesses}

        for url in accessed_urls:
            source = self.get_source(url)
            if source:
                # Generate citation text (basic APA format)
                citation_text = f"{source.author or 'Unknown Author'}. "
                if source.publication_date:
                    citation_text += f"({source.publication_date}). "
                citation_text += f"{source.title}. Retrieved from {source.url}"

                citation = ResearchCitation(
                    source=source, citation_text=citation_text, citation_style="APA"
                )
                citations.append(citation)

        return citations

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the agent tracker to a dictionary for persistence.

        Returns:
            dict: Serializable dictionary representation of the tracker.
        """
        return {
            "agent_id": self.agent_id,
            "local_accesses": [access.model_dump() for access in self._local_accesses],
            "local_sources": {url: source.model_dump() for url, source in self._local_sources.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], shared_registry: SharedSourceRegistry) -> "AgentSourceTracker":
        """
        Restore the agent tracker from a serialized dictionary.

        Args:
            data (dict): Dictionary representation from to_dict().
            shared_registry (SharedSourceRegistry): Shared registry for coordination.

        Returns:
            AgentSourceTracker: Restored tracker instance.
        """
        tracker = cls(data["agent_id"], shared_registry)

        # Restore local accesses
        for access_data in data.get("local_accesses", []):
            access = SourceAccess.model_validate(access_data)
            tracker._local_accesses.append(access)

        # Restore local sources
        for url, source_data in data.get("local_sources", {}).items():
            source = ResearchSource.model_validate(source_data)
            tracker._local_sources[url] = source

        return tracker

    def clear_local_data(self) -> None:
        """Clear local tracking data (for cleanup after task completion)."""
        self._local_accesses.clear()
        self._local_sources.clear()
        logger.info(f"Cleared local data for agent {self.agent_id}")


# Module exports
__all__ = [
    "SourceAccess",
    "SharedSourceRegistry",
    "AgentSourceTracker",
]
