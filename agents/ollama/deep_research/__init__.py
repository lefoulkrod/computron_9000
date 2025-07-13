"""
Deep Research Agent package.

This module provides a multi-agent system for conducting thorough research
across multiple sources to provide comprehensive, well-sourced answers to
complex queries.

The main entry point is the deep_research_agent_tool function which provides
access to the full multi-agent research capabilities.
"""

# Only export the tool function for external use
from .agent import deep_research_agent, deep_research_agent_tool

__all__ = [
    "deep_research_agent_tool",
    "deep_research_agent",
]
