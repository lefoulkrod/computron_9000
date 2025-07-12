"""
Tool wrappers with source tracking for the Deep Research Agent.

This module wraps standard web tools to automatically track source usage
for citation and credibility assessment.
"""

import logging
import functools
from typing import List, Optional, Dict, Callable, Any

from agents.ollama.deep_research.source_tracker import SourceTracker
from tools.web import (
    search_google, 
    get_webpage, 
    get_webpage_summary,
    get_webpage_summary_sections,
    get_webpage_substring,
    html_find_elements,
    GoogleSearchResults,
    HtmlElementResult,
)
from tools.web.types import ReducedWebpage
from tools.web.summarize import SectionSummary

logger = logging.getLogger(__name__)

class TrackedWebTools:
    """
    Class that provides web tools with automatic source tracking.
    """
    
    def __init__(self, source_tracker: SourceTracker):
        """
        Initialize tracked web tools with a source tracker.
        
        Args:
            source_tracker (SourceTracker): The source tracker to use
        """
        self.source_tracker = source_tracker
    
    async def search_google(self, query: str, max_results: int = 5) -> GoogleSearchResults:
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
                url=result.link, 
                tool_name="search_google", 
                query=query
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
        return await get_webpage(url=url)
    
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
    
    async def get_webpage_summary_sections(self, url: str) -> List[SectionSummary]:
        """
        Get webpage section summaries with automatic source tracking.
        
        Args:
            url (str): The URL to summarize
            
        Returns:
            List[SectionSummary]: The section summaries
        """
        self.source_tracker.register_access(url=url, tool_name="get_webpage_summary_sections")
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
        self, html: str, tag: str, text: Optional[str] = None
    ) -> List[HtmlElementResult]:
        """
        Find HTML elements with automatic source tracking.
        
        Note: This doesn't track a URL directly as it operates on HTML content.
        
        Args:
            html (str): The HTML content
            tag (str): The HTML tag to search for
            text (Optional[str]): Optional text content to match
            
        Returns:
            List[HtmlElementResult]: The matching HTML elements
        """
        # Note: No direct URL to track
        return await html_find_elements(html=html, tag=tag, text=text)


# Create wrapped versions of web tools that automatically track source usage

async def tracked_search_google(source_tracker: SourceTracker, query: str, max_results: int = 5) -> GoogleSearchResults:
    """
    Search Google with automatic source tracking.
    
    Args:
        source_tracker (SourceTracker): The source tracker instance
        query (str): The search query
        max_results (int): Maximum number of results to return
        
    Returns:
        GoogleSearchResults: The search results
    """
    results = await search_google(query=query, max_results=max_results)
    # We don't track the search itself, but record it with each result URL
    for result in results.results:
        source_tracker.register_access(
            url=result.link, 
            tool_name="search_google", 
            query=query
        )
    return results


def get_tracked_web_tools(source_tracker: SourceTracker) -> Dict[str, Callable]:
    """
    Get a dictionary of web tools with source tracking.
    
    Args:
        source_tracker (SourceTracker): The source tracker to use
        
    Returns:
        Dict[str, Callable]: Dictionary of tracked tool functions
    """
    tracked_tools = TrackedWebTools(source_tracker)
    
    return {
        "search_google": tracked_tools.search_google,
        "get_webpage": tracked_tools.get_webpage,
        "get_webpage_summary": tracked_tools.get_webpage_summary,
        "get_webpage_summary_sections": tracked_tools.get_webpage_summary_sections,
        "get_webpage_substring": tracked_tools.get_webpage_substring,
        "html_find_elements": tracked_tools.html_find_elements,
    }
