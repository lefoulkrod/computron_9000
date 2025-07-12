"""
Tool documentation access functionality for the Deep Research Agent.

This module provides utility functions to access tool documentation at runtime,
allowing the agent to get guidance on tool usage when needed.
"""

import logging
import os
from typing import Dict, Optional, List, Union
import re

logger = logging.getLogger(__name__)

# Path to the tool documentation file, relative to this module
TOOL_DOC_PATH = os.path.join(os.path.dirname(__file__), "tool_documentation.md")

class ToolDocumentation:
    """Class to access and query the tool documentation."""
    
    def __init__(self, doc_path: str = TOOL_DOC_PATH):
        """
        Initialize the tool documentation accessor.
        
        Args:
            doc_path (str): Path to the tool documentation Markdown file
        """
        self.doc_path = doc_path
        self._docs_cache = None
        self._section_map = {}
        self._load_documentation()
    
    def _load_documentation(self) -> None:
        """Load the tool documentation from file."""
        try:
            with open(self.doc_path, 'r') as f:
                self._docs_cache = f.read()
                
            # Parse the documentation to build section mappings
            self._build_section_map()
            logger.info(f"Successfully loaded tool documentation from {self.doc_path}")
        except Exception as e:
            logger.error(f"Failed to load tool documentation: {e}")
            self._docs_cache = "# Tool Documentation Not Available"
    
    def _build_section_map(self) -> None:
        """Build a map of tool names to their documentation sections."""
        if not self._docs_cache:
            return
        
        # Find all tool documentation sections
        tool_sections = re.split(r'### ', self._docs_cache)
        
        # Skip the first element which is everything before the first tool section
        for section in tool_sections[1:]:
            # Extract the tool name from the first line
            tool_name = section.strip().split('\n')[0]
            self._section_map[tool_name] = "### " + section
    
    def get_full_documentation(self) -> str:
        """
        Get the complete tool documentation.
        
        Returns:
            str: The complete tool documentation in Markdown format
        """
        return self._docs_cache or "Documentation not available."
    
    def get_tool_documentation(self, tool_name: str) -> str:
        """
        Get documentation for a specific tool.
        
        Args:
            tool_name (str): The name of the tool
            
        Returns:
            str: The tool-specific documentation in Markdown format
        """
        # Check if we need to reload the documentation
        if self._docs_cache is None:
            self._load_documentation()
        
        # Try to find the exact tool name
        if tool_name in self._section_map:
            return self._section_map[tool_name]
        
        # Try to find a partial match
        for name, section in self._section_map.items():
            if tool_name.lower() in name.lower():
                return section
        
        return f"Documentation for {tool_name} not found."
    
    def get_integration_patterns(self) -> str:
        """
        Get the tool integration patterns section.
        
        Returns:
            str: The tool integration patterns documentation
        """
        if self._docs_cache is None:
            self._load_documentation()
            
        if not self._docs_cache:
            return "Documentation not available."
        
        # Extract the integration patterns section
        pattern = r'## Tool Integration Patterns(.*?)(?:^##|\Z)'
        match = re.search(pattern, self._docs_cache, re.DOTALL | re.MULTILINE)
        if match:
            return "## Tool Integration Patterns" + match.group(1)
        
        return "Integration patterns documentation not found."
    
    def get_citation_best_practices(self) -> str:
        """
        Get the citation best practices section.
        
        Returns:
            str: The citation best practices documentation
        """
        if self._docs_cache is None:
            self._load_documentation()
            
        if not self._docs_cache:
            return "Documentation not available."
        
        # Extract the citation best practices section
        pattern = r'## Source Citation Best Practices(.*?)(?:^##|\Z)'
        match = re.search(pattern, self._docs_cache, re.DOTALL | re.MULTILINE)
        if match:
            return "## Source Citation Best Practices" + match.group(1)
        
        return "Citation best practices documentation not found."
    
    def search_documentation(self, query: str) -> str:
        """
        Search the documentation for a specific query.
        
        Args:
            query (str): The search query
            
        Returns:
            str: Relevant documentation sections matching the query
        """
        if self._docs_cache is None:
            self._load_documentation()
        
        query_terms = query.lower().split()
        results = []
        
        # Search each section for query terms
        for name, section in self._section_map.items():
            section_lower = section.lower()
            matches = sum(term in section_lower for term in query_terms)
            if matches > 0:
                results.append((matches, name, section))
        
        # Sort by relevance (number of matching terms)
        results.sort(reverse=True)
        
        if not results:
            return f"No documentation found for query: {query}"
        
        # Return the top 2 most relevant sections
        return "\n\n---\n\n".join([section for _, _, section in results[:2]])


# Create a singleton instance for use throughout the module
tool_docs = ToolDocumentation()


async def get_tool_documentation(tool_name: str = "") -> str:
    """
    Get documentation for a specific tool or general tool usage.
    
    Args:
        tool_name (str): The name of the tool to get documentation for,
                         or empty string for general tool information
    
    Returns:
        str: The requested tool documentation
    """
    if not tool_name:
        return tool_docs.get_integration_patterns()
    
    return tool_docs.get_tool_documentation(tool_name)


async def search_tool_documentation(query: str) -> str:
    """
    Search the tool documentation for relevant information.
    
    Args:
        query (str): The search query
    
    Returns:
        str: Relevant documentation sections
    """
    return tool_docs.search_documentation(query)


async def get_citation_practices() -> str:
    """
    Get documentation on citation best practices.
    
    Returns:
        str: Citation best practices documentation
    """
    return tool_docs.get_citation_best_practices()


# Export the public API functions
__all__ = [
    "get_tool_documentation",
    "search_tool_documentation", 
    "get_citation_practices",
]
