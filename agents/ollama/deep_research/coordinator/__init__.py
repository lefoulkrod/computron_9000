"""
Research Coordinator Agent module.

This module provides the Research Coordinator Agent that orchestrates
multi-agent deep research workflows.
"""

from .agent import (
    coordination_tools,
    research_coordinator_after_callback,
    research_coordinator_agent,
    research_coordinator_before_callback,
    research_coordinator_tool,
)
from .coordination_tools import CoordinationTools
from .workflow_coordinator import ConcreteResearchWorkflowCoordinator

__all__ = [
    "research_coordinator_agent",
    "research_coordinator_before_callback",
    "research_coordinator_after_callback",
    "research_coordinator_tool",
    "coordination_tools",
    "CoordinationTools",
    "ConcreteResearchWorkflowCoordinator",
]
