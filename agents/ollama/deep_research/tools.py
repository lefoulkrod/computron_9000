"""
Tool utility functions for the Deep Research Agent.

This module provides utility functions for accessing tool documentation
and citation practices for the Deep Research Agent.
"""

import logging
import re
from typing import Optional

from agents.ollama.deep_research.source_tracker import SourceTracker

logger = logging.getLogger(__name__)

# Tool documentation content
TOOL_DOCUMENTATION = """
# Web Research Tools Documentation

This document provides detailed documentation for the web research tools used by the Deep Research Agent.

## Tool Overview

| Tool | Purpose | Key Features |
|------|---------|--------------|
| `search_google` | Find relevant web pages for a topic | Results include title, URL, and snippet |
| `get_webpage` | Extract full text content from a URL | Removes HTML, preserves text, extracts links |
| `get_webpage_summary` | Generate concise summary of a webpage | Handles large pages via section summaries |
| `get_webpage_summary_sections` | Get sectional summaries with position data | Useful for navigating long documents |
| `get_webpage_substring` | Extract specific portions of a webpage | Allows targeting specific content sections |
| `html_find_elements` | Extract specific HTML elements | Find elements by tag and content |
| `assess_webpage_credibility` | Evaluate the credibility of a webpage | Analyzes domain reputation, content quality, citations |
| `extract_webpage_metadata` | Extract comprehensive metadata from a webpage | Gets author, publication date, description, keywords |
| `categorize_source` | Categorize a source by type and authority | Determines primary type, authority level, content type |
| `search_reddit` | Find relevant Reddit posts for a topic | Results include title, content, author, and score |
| `get_reddit_comments_tree_shallow` | Get comments for a Reddit post | Returns a shallow tree of comments and replies |
| `analyze_reddit_credibility` | Evaluate credibility of Reddit sources | Analyzes post age, karma, comment ratio |
| `analyze_comment_sentiment` | Analyze sentiment in Reddit comments | Provides sentiment analysis for comments |

## Source Analysis Guidelines

When analyzing sources for research:

1. **Always Start with Metadata Extraction**: Use `extract_webpage_metadata` to gather basic information
2. **Categorize for Context**: Use `categorize_source` to understand the source type and authority level
3. **Assess Credibility**: Use `assess_webpage_credibility` for detailed reliability evaluation
4. **Follow a Systematic Approach**: 
   - High authority + high credibility = primary citations
   - Medium authority + medium credibility = supporting evidence  
   - Low authority or credibility = supplementary use only
5. **Check Citation Readiness**: Ensure author and publication date are available
6. **Consider Temporal Relevance**: Prefer recent sources for current topics
7. **Balance Source Types**: Mix academic, news, and expert sources appropriately

## Social Media Research Guidelines

When researching on social platforms like Reddit:

1. **Verify Information**: Cross-reference claims with authoritative sources
2. **Consider Source Quality**: Evaluate user history, karma, and community standing
3. **Check Community Reputation**: Assess the subreddit's moderation policies and topic focus
4. **Look for Consensus**: Value information confirmed by multiple independent users
5. **Be Aware of Bias**: Consider potential community bias in specialized subreddits
6. **Evaluate Recency**: Check post/comment dates for time-sensitive information
7. **Follow Citation Chains**: Look for linked sources in comments and verify them
8. **Consider Expertise Signals**: Look for flaired users or those with demonstrated expertise
9. **Evaluate Response Quality**: Well-sourced, detailed responses typically have more value
10. **Use Multiple Platforms**: Compare findings across different social platforms and traditional sources

## Citation Best Practices

When citing sources in research:

1. **Include Complete Information**: Always provide full source details (author, title, date, URL)
2. **Use Consistent Format**: Follow established citation styles like APA or MLA consistently
3. **Cite Primary Sources**: Whenever possible, cite original research rather than summaries
4. **Include Access Dates**: For web content, include the date you accessed the information
5. **Provide Context**: Explain how each source contributes to your findings
6. **Evaluate Source Quality**: Consider the credibility, expertise, and potential bias of each source
7. **Balance Sources**: Use a mix of academic, journalistic, and expert sources when appropriate
8. **Update Citations**: If sources are updated or corrected, update your citations accordingly
"""

# Citation practices documentation
CITATION_PRACTICES = """
# Citation Best Practices

When citing sources in research:

1. **Include Complete Information**: Always provide full source details (author, title, date, URL)
2. **Use Consistent Format**: Follow established citation styles like APA or MLA consistently
3. **Cite Primary Sources**: Whenever possible, cite original research rather than summaries
4. **Include Access Dates**: For web content, include the date you accessed the information
5. **Provide Context**: Explain how each source contributes to your findings
6. **Evaluate Source Quality**: Consider the credibility, expertise, and potential bias of each source
7. **Balance Sources**: Use a mix of academic, journalistic, and expert sources when appropriate
8. **Update Citations**: If sources are updated or corrected, update your citations accordingly

## APA Style Format (7th Edition)

For webpages with author:
Author, A. A. (Year, Month Day). Title of webpage. Website Name. URL

For webpages without author:
Title of webpage. (Year, Month Day). Website Name. URL

For articles:
Author, A. A. (Year). Title of article. Title of Journal, volume(issue), page range. URL or DOI

For Reddit posts:
Username. (Year, Month Day). Title of post [Post]. Reddit. URL

## MLA Style Format (9th Edition)

For webpages with author:
Author. "Title of Webpage." Website Name, Publisher (if different from website name), Date published, URL. Accessed Day Month Year.

For webpages without author:
"Title of Webpage." Website Name, Publisher (if different), Date published, URL. Accessed Day Month Year.

For Reddit posts:
Username. "Title of Post." Reddit, Subreddit Name, Date posted, URL. Accessed Day Month Year.
"""


async def get_tool_documentation(tool_name: str = "") -> str:
    """
    Get detailed documentation for available research tools.
    
    Args:
        tool_name (str): Optional name of specific tool to get documentation for
        
    Returns:
        str: Markdown documentation of research tools.
    """
    if not tool_name:
        return TOOL_DOCUMENTATION
        
    # If a specific tool is requested, try to find its section
    pattern = rf"### {re.escape(tool_name)}(.*?)(?:^###|\Z)"
    match = re.search(pattern, TOOL_DOCUMENTATION, re.DOTALL | re.MULTILINE)
    if match:
        return f"### {tool_name}{match.group(1)}"
    
    # Try a partial match if exact match fails
    for tool in ["search_google", "get_webpage", "get_webpage_summary", "get_webpage_summary_sections",
                "get_webpage_substring", "html_find_elements", "assess_webpage_credibility", 
                "extract_webpage_metadata", "categorize_source", "search_reddit", 
                "get_reddit_comments_tree_shallow", "analyze_reddit_credibility", "analyze_comment_sentiment"]:
        if tool_name.lower() in tool.lower():
            pattern = rf"### {re.escape(tool)}(.*?)(?:^###|\Z)"
            match = re.search(pattern, TOOL_DOCUMENTATION, re.DOTALL | re.MULTILINE)
            if match:
                return f"### {tool}{match.group(1)}"
    
    return f"Documentation for {tool_name} not found."


async def search_tool_documentation(query: str) -> str:
    """
    Search for specific information in the tool documentation.
    
    Args:
        query (str): The search query.
        
    Returns:
        str: Relevant documentation sections matching the query.
    """
    # Simple search implementation
    query_terms = query.lower().split()
    
    # Split documentation into sections
    sections = re.split(r'\n#{2,3} ', TOOL_DOCUMENTATION)
    
    matching_sections = []
    for section in sections:
        if any(term in section.lower() for term in query_terms):
            # Add the heading syntax back
            if not section.startswith('#'):
                section = "## " + section
            matching_sections.append(section)
    
    if not matching_sections:
        return "No matching documentation found. Try a different search term."
    
    return "\n\n".join(matching_sections)


async def get_citation_practices() -> str:
    """
    Get guidelines for properly citing research sources.
    
    Returns:
        str: Markdown documentation of citation best practices.
    """
    return CITATION_PRACTICES


# Module exports
__all__ = [
    "get_tool_documentation",
    "search_tool_documentation", 
    "get_citation_practices",
]
