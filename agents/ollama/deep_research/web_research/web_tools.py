"""
Web research tools and functionality.

This module provides tools for web-based research with agent-specific source tracking.
Migrated from tracked_tools.py as part of Phase 3.2 tool migration refactors.
"""

import logging
from datetime import datetime
from typing import Any

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker
from agents.ollama.deep_research.source_analysis import (
    CredibilityAssessment,
    SourceCategorization,
    WebpageMetadata,
    assess_webpage_credibility,
    categorize_source,
    extract_webpage_metadata,
)
from tools.web import (
    GoogleSearchResults,
    HtmlElementResult,
    get_webpage,
    get_webpage_substring,
    get_webpage_summary,
    get_webpage_summary_sections,
    html_find_elements,
    search_google,
)
from tools.web.summarize import SectionSummary
from tools.web.types import ReducedWebpage

logger = logging.getLogger(__name__)


class WebResearchTools:
    """
    Web research tools with agent-specific source tracking.

    This class provides web research capabilities for the Web Research Agent,
    migrated from the centralized TrackedWebTools implementation.
    """

    def __init__(self, source_tracker: AgentSourceTracker):
        """
        Initialize web research tools with an agent-specific source tracker.

        Args:
            source_tracker (AgentSourceTracker): The agent-specific source tracker to use
        """
        self.source_tracker = source_tracker

    async def search_google(
        self, query: str, max_results: int = 5
    ) -> GoogleSearchResults:
        """
        Search Google with automatic source tracking.

        Args:
            query (str): The search query
            max_results (int): Maximum number of results to return

        Returns:
            GoogleSearchResults: The search results
        """
        results = await search_google(query=query, max_results=max_results)
        # Track each result URL with the query that found it
        for result in results.results:
            self.source_tracker.register_access(
                url=result.link, tool_name="search_google", query=query
            )
        return results

    async def get_webpage(self, url: str) -> ReducedWebpage:
        """
        Get webpage content with automatic source tracking.

        Args:
            url (str): The URL to fetch

        Returns:
            ReducedWebpage: The webpage content
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage")
        webpage_result: ReducedWebpage = await get_webpage(url=url)
        return webpage_result

    async def get_webpage_summary(self, url: str) -> str:
        """
        Get webpage summary with automatic source tracking.

        Args:
            url (str): The URL to summarize

        Returns:
            str: The webpage summary
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_summary")
        return await get_webpage_summary(url=url)

    async def get_webpage_summary_sections(self, url: str) -> list[SectionSummary]:
        """
        Get webpage section summaries with automatic source tracking.

        Args:
            url (str): The URL to summarize

        Returns:
            list[SectionSummary]: The section summaries
        """
        self.source_tracker.register_access(
            url=url, tool_name="get_webpage_summary_sections"
        )
        return await get_webpage_summary_sections(url=url)

    async def get_webpage_substring(self, url: str, start: int, end: int) -> str:
        """
        Get webpage substring with automatic source tracking.

        Args:
            url (str): The URL to fetch
            start (int): Start index
            end (int): End index

        Returns:
            str: The substring
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_substring")
        return await get_webpage_substring(url=url, start=start, end=end)

    async def html_find_elements(
        self, html: str, tag: str | list[str], text: str | None = None
    ) -> list[HtmlElementResult]:
        """
        Find HTML elements with automatic source tracking.

        Note: This doesn't track a URL directly as it operates on HTML content.

        Args:
            html (str): The HTML content
            tag (str | list[str]): The HTML tag(s) or CSS selector(s) to search for
            text (str | None): Optional text content to match

        Returns:
            list[HtmlElementResult]: The matching HTML elements
        """
        # Note: No direct URL to track
        return await html_find_elements(html=html, selectors=tag, text=text)

    async def assess_webpage_credibility(self, url: str) -> CredibilityAssessment:
        """
        Assess webpage credibility with automatic source tracking.

        Args:
            url (str): The URL to assess

        Returns:
            CredibilityAssessment: Credibility assessment results
        """
        self.source_tracker.register_access(
            url=url, tool_name="assess_webpage_credibility"
        )
        return await assess_webpage_credibility(url=url)

    async def extract_webpage_metadata(self, url: str) -> WebpageMetadata:
        """
        Extract webpage metadata with automatic source tracking.

        Args:
            url (str): The URL to analyze

        Returns:
            WebpageMetadata: Extracted metadata
        """
        self.source_tracker.register_access(
            url=url, tool_name="extract_webpage_metadata"
        )
        return await extract_webpage_metadata(url=url)

    async def categorize_source(
        self, url: str, metadata: WebpageMetadata | None = None
    ) -> SourceCategorization:
        """
        Categorize a source with automatic source tracking.

        Args:
            url (str): The URL of the source
            metadata (WebpageMetadata | None): Extracted metadata. If None, will extract metadata first.

        Returns:
            SourceCategorization: Source categorization results
        """
        self.source_tracker.register_access(url=url, tool_name="categorize_source")

        # If metadata is not provided, extract it first
        if metadata is None:
            metadata = await self.extract_webpage_metadata(url)

        return categorize_source(url=url, metadata=metadata)

    # Citation management functionality (migrated from legacy Citation Manager)
    async def generate_web_citation(
        self, url: str, style: str = "APA"
    ) -> dict[str, Any]:
        """
        Generate a properly formatted citation for a web source.

        Args:
            url (str): The URL to generate citation for
            style (str): Citation style (APA, MLA, Chicago)

        Returns:
            Dict[str, Any]: Formatted citation information
        """
        try:
            metadata = await self.extract_webpage_metadata(url)

            # Format citation based on style
            if style.upper() == "APA":
                citation = self._format_apa_citation(metadata)
            elif style.upper() == "MLA":
                citation = self._format_mla_citation(metadata)
            elif style.upper() == "CHICAGO":
                citation = self._format_chicago_citation(metadata)
            else:
                citation = self._format_apa_citation(metadata)  # Default to APA

            return {
                "url": url,
                "style": style,
                "formatted_citation": citation,
                "metadata": metadata,
                "access_date": datetime.now().strftime("%Y-%m-%d"),
            }

        except Exception as e:
            logger.error(f"Error generating citation for {url}: {e}")
            return {
                "url": url,
                "style": style,
                "formatted_citation": f"Error generating citation: {str(e)}",
                "metadata": {},
                "access_date": datetime.now().strftime("%Y-%m-%d"),
            }

    def _format_apa_citation(self, metadata: WebpageMetadata) -> str:
        """Format citation in APA style."""
        author = metadata["author"] or ""
        title = metadata["title"] or "Untitled"
        publisher = metadata["publisher"] or metadata["domain"]
        date = metadata["publication_date"] or "n.d."
        url = metadata["url"]

        if author:
            return f"{author}. ({date}). {title}. {publisher}. {url}"
        return f"{title}. ({date}). {publisher}. {url}"

    def _format_mla_citation(self, metadata: WebpageMetadata) -> str:
        """Format citation in MLA style."""
        author = metadata["author"] or ""
        title = metadata["title"] or "Untitled"
        publisher = metadata["publisher"] or metadata["domain"]
        date = metadata["publication_date"] or ""
        url = metadata["url"]
        access_date = datetime.now().strftime("%d %b %Y")

        if author:
            return f'{author}. "{title}." {publisher}, {date}, {url}. Accessed {access_date}.'
        return f'"{title}." {publisher}, {date}, {url}. Accessed {access_date}.'

    def _format_chicago_citation(self, metadata: WebpageMetadata) -> str:
        """Format citation in Chicago style."""
        author = metadata["author"] or ""
        title = metadata["title"] or "Untitled"
        publisher = metadata["publisher"] or metadata["domain"]
        date = metadata["publication_date"] or ""
        url = metadata["url"]
        access_date = datetime.now().strftime("%B %d, %Y")

        if author:
            return f'{author}. "{title}." {publisher}. {date}. {url} (accessed {access_date}).'
        return f'"{title}." {publisher}. {date}. {url} (accessed {access_date}).'

    async def get_citation_guidelines(self) -> str:
        """
        Get guidelines for properly citing web sources.

        Returns:
            str: Citation guidelines and best practices
        """
        return """# Citation Guidelines for Web Sources

## APA Style (7th Edition)
For webpages with author:
Author, A. A. (Year, Month Day). Title of webpage. Website Name. URL

For webpages without author:
Title of webpage. (Year, Month Day). Website Name. URL

## MLA Style (9th Edition)
For webpages with author:
Author. "Title of Webpage." Website Name, Date published, URL. Accessed Day Month Year.

For webpages without author:
"Title of Webpage." Website Name, Date published, URL. Accessed Day Month Year.

## Chicago Style
For webpages with author:
Author. "Title of Webpage." Website Name. Date published. URL (accessed Month Day, Year).

## Best Practices
1. Always include access dates for web content
2. Verify author and publication date information
3. Use consistent formatting throughout your bibliography
4. Prefer primary sources when available
5. Include DOI when available instead of URL
"""


# Module exports
__all__ = [
    "WebResearchTools",
]
