"""
Source tracking functionality for the Deep Research Agent.

This module provides tools to track web sources accessed during research
and manage citation information for proper attribution.
"""

import logging
import time
from datetime import datetime

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
    """

    url: str
    tool_name: str
    timestamp: float
    query: str | None = None

    @property
    def access_datetime(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.timestamp)

    @property
    def formatted_access_time(self) -> str:
        """Return formatted access time string."""
        return self.access_datetime.strftime("%Y-%m-%d %H:%M:%S")


class SourceTracker:
    """
    Tracks sources accessed during research sessions.

    This class maintains a registry of all sources accessed during a research session,
    including which tools were used to access them, when they were accessed, and what
    information was extracted.
    """

    def __init__(self) -> None:
        """Initialize an empty source tracker."""
        self._sources: dict[str, ResearchSource] = {}  # url -> ResearchSource
        self._accesses: list[SourceAccess] = []  # All source accesses
        self._url_tools: dict[str, set[str]] = {}  # url -> set of tools used

    def register_access(
        self, url: str, tool_name: str, query: str | None = None
    ) -> None:
        """
        Register a source access with the tracking system.

        Args:
            url (str): The URL of the source accessed.
            tool_name (str): The name of the tool used to access the source.
            query (Optional[str]): The query or parameters used, if applicable.
        """
        # Create source access record
        access = SourceAccess(
            url=url, tool_name=tool_name, timestamp=time.time(), query=query
        )

        # Add to access log
        self._accesses.append(access)

        # Update tools used for this URL
        if url not in self._url_tools:
            self._url_tools[url] = set()
        self._url_tools[url].add(tool_name)

        logger.info(f"Registered source access: {url} via {tool_name}")

    def register_source(self, source: ResearchSource) -> None:
        """
        Register a source with the tracking system.

        Args:
            source (ResearchSource): The source to register.
        """
        self._sources[source.url] = source
        logger.info(f"Registered research source: {source.title} ({source.url})")

    def get_source(self, url: str) -> ResearchSource | None:
        """
        Get a registered source by URL.

        Args:
            url (str): The URL of the source to retrieve.

        Returns:
            Optional[ResearchSource]: The source if found, None otherwise.
        """
        return self._sources.get(url)

    def get_sources(self) -> list[ResearchSource]:
        """
        Get all registered sources.

        Returns:
            List[ResearchSource]: List of all registered sources.
        """
        return list(self._sources.values())

    def get_tools_for_url(self, url: str) -> list[str]:
        """
        Get all tools used to access a specific URL.

        Args:
            url (str): The URL to check.

        Returns:
            List[str]: List of tool names used to access the URL.
        """
        return list(self._url_tools.get(url, set()))

    def get_accesses(self, url: str | None = None) -> list[SourceAccess]:
        """
        Get all source accesses, optionally filtered by URL.

        Args:
            url (Optional[str]): The URL to filter by, or None for all accesses.

        Returns:
            List[SourceAccess]: List of source accesses.
        """
        if url:
            return [access for access in self._accesses if access.url == url]
        return self._accesses

    def format_citation(self, url: str, style: str = "APA") -> ResearchCitation | None:
        """
        Format a citation for a source in the specified style.

        Args:
            url (str): The URL of the source to cite.
            style (str): The citation style to use (default: APA).

        Returns:
            Optional[ResearchCitation]: The formatted citation, or None if source not found.
        """
        source = self.get_source(url)
        if not source:
            return None

        if style.upper() == "APA":
            return self._format_apa_citation(source)
        if style.upper() == "MLA":
            return self._format_mla_citation(source)
        # Default to APA if style not recognized
        return self._format_apa_citation(source)

    def _format_apa_citation(self, source: ResearchSource) -> ResearchCitation:
        """
        Format a citation in APA style.

        Args:
            source (ResearchSource): The source to format.

        Returns:
            ResearchCitation: The formatted citation.
        """
        # Determine components
        author = source.author or "n.d."
        year = (
            f"({source.publication_date.split('-')[0]})"
            if source.publication_date
            else "(n.d.)"
        )
        title = source.title

        # Build citation text
        if source.author:
            citation_text = f"{author} {year}. {title}. Retrieved from {source.url}"
        else:
            citation_text = f"{title}. {year}. Retrieved from {source.url}"

        return ResearchCitation(
            source=source, citation_text=citation_text, citation_style="APA"
        )

    def _format_mla_citation(self, source: ResearchSource) -> ResearchCitation:
        """
        Format a citation in MLA style.

        Args:
            source (ResearchSource): The source to format.

        Returns:
            ResearchCitation: The formatted citation.
        """
        # Determine components
        author = source.author or "n.a."
        title = f'"{source.title}"'
        access_date = datetime.now().strftime("%d %b. %Y")

        # Build citation text
        if source.author:
            citation_text = f"{author}. {title}. {source.publication_date or 'n.d.'}, {source.url}. Accessed {access_date}."
        else:
            citation_text = f"{title}. {source.publication_date or 'n.d.'}, {source.url}. Accessed {access_date}."

        return ResearchCitation(
            source=source, citation_text=citation_text, citation_style="MLA"
        )

    def generate_bibliography(self, style: str = "APA") -> list[ResearchCitation]:
        """
        Generate a bibliography with all sources.

        Args:
            style (str): The citation style to use (default: APA).

        Returns:
            List[ResearchCitation]: List of formatted citations.
        """
        bibliography = []
        for url in self._sources:
            citation = self.format_citation(url, style)
            if citation:
                bibliography.append(citation)
        return bibliography

    def clear(self) -> None:
        """Clear all tracked sources and accesses."""
        self._sources.clear()
        self._accesses.clear()
        self._url_tools.clear()
        logger.info("Source tracker cleared")
