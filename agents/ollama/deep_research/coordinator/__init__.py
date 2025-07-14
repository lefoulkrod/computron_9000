"""
Research Coordinator Agent module.

This module provides the Research Coordinator Agent that orchestrates
multi-agent deep research workflows.

This module is internal to the deep_research package.
"""

# Internal imports only - not exposed outside deep_research package
from .agent import (
    coordination_tools,
    research_coordinator_after_callback,
    research_coordinator_agent,
    research_coordinator_before_callback,
    research_coordinator_tool,
)
from .coordination_tools import CoordinationTools

# Internal module - exports available for use within deep_research package only
__all__ = [
    "coordination_tools",
    "research_coordinator_after_callback",
    "research_coordinator_agent",
    "research_coordinator_before_callback",
    "research_coordinator_tool",
    "CoordinationTools",
]
