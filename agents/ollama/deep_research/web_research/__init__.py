"""
Web Research Agent module.

This module provides the Web Research Agent specialized for conducting
research using web sources with source tracking and credibility assessment.
"""

from .agent import (
    web_research_agent,
    web_research_tool,
)

__all__ = [
    "web_research_agent",
    "web_research_tool",
]
