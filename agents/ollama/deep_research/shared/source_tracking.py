"""
Shared source tracking infrastructure for multi-agent research system.

This module provides agent-specific source trackers and a shared source registry
to avoid conflicts between agents while enabling source deduplication.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

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
    query: Optional[str] = None

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
        self._sources: Dict[str, ResearchSource] = {}  # url -> ResearchSource
        self._all_accesses: List[SourceAccess] = []  # All source accesses across agents
        self._agent_accesses: Dict[str, List[SourceAccess]] = {}  # agent_id -> accesses

    def register_source(self, source: ResearchSource) -> None:
        """
        Register a source in the shared registry.

        Args:
            source (ResearchSource): The source to register.
        """
        self._sources[source.url] = source
        logger.info(f"Registered shared source: {source.title} ({source.url})")

    def get_source(self, url: str) -> Optional[ResearchSource]:
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

    def get_all_sources(self) -> List[ResearchSource]:
        """Get all sources in the registry."""
        return list(self._sources.values())

    def get_accesses_by_agent(self, agent_id: str) -> List[SourceAccess]:
        """Get all accesses by a specific agent."""
        return self._agent_accesses.get(agent_id, [])

    def get_all_accesses(self) -> List[SourceAccess]:
        """Get all source accesses across all agents."""
        return self._all_accesses

    def get_accessing_agents(self, url: str) -> Set[str]:
        """Get set of agent IDs that have accessed a specific URL."""
        return {access.agent_id for access in self._all_accesses if access.url == url}


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
        self._local_accesses: List[SourceAccess] = []  # This agent's accesses
        self._local_sources: Dict[str, ResearchSource] = {}  # This agent's sources

    def register_access(
        self, url: str, tool_name: str, query: Optional[str] = None
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
            query=query
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

        logger.info(f"Agent {self.agent_id} registered source: {source.title} ({source.url})")

    def get_source(self, url: str) -> Optional[ResearchSource]:
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

    def get_local_accesses(self) -> List[SourceAccess]:
        """Get all accesses made by this agent."""
        return self._local_accesses.copy()

    def get_local_sources(self) -> List[ResearchSource]:
        """Get all sources registered by this agent."""
        return list(self._local_sources.values())

    def has_accessed(self, url: str) -> bool:
        """Check if this agent has accessed a specific URL."""
        return any(access.url == url for access in self._local_accesses)

    def get_citations(self) -> List[ResearchCitation]:
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
                    source=source,
                    citation_text=citation_text,
                    citation_style="APA"
                )
                citations.append(citation)
        
        return citations

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
