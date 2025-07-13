"""
Web Research Agent module.

This module provides the Web Research Agent specialized for conducting
research using web sources with source tracking and credibility assessment.
"""

from .agent import (
    web_research_after_callback,
    web_research_agent,
    web_research_before_callback,
    web_research_tool,
    web_source_tracker,
)
from .web_tools import WebResearchTools

__all__ = [
    "web_research_agent",
    "web_research_before_callback",
    "web_research_after_callback",
    "web_research_tool",
    "web_source_tracker",
    "WebResearchTools",
]
