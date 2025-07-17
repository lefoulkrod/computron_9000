"""Deep Research Agent package.

This module provides a multi-agent system for conducting thorough research
across multiple sources to provide comprehensive, well-sourced answers to
complex queries.

The main entry point is the research_coordinator_tool function which provides
access to the full multi-agent research capabilities through the Research
Coordinator Agent.
"""

# Export the Research Coordinator Agent as the primary interface
from .coordinator import (
    research_coordinator_agent,
    research_coordinator_tool,
)

# Backward compatibility aliases (to be removed in future version)
deep_research_agent = research_coordinator_agent
deep_research_agent_tool = research_coordinator_tool

__all__ = [
    "deep_research_agent",
    # Backward compatibility exports
    "deep_research_agent_tool",
    "research_coordinator_agent",
    "research_coordinator_tool",
]
