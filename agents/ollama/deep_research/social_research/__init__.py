"""
Social Research Agent module.

This module provides the Social Research Agent specialized for conducting
research using social media and forum sources with sentiment analysis.
"""

from .agent import (
    social_research_after_callback,
    social_research_agent,
    social_research_before_callback,
    social_research_tool,
    social_source_tracker,
)
from .social_tools import SocialResearchTools

__all__ = [
    "social_research_agent",
    "social_research_before_callback",
    "social_research_after_callback",
    "social_research_tool",
    "social_source_tracker",
    "SocialResearchTools",
]
