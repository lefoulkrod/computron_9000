"""
Deep Research Agent package.

This module provides a specialized agent for conducting thorough research
across multiple sources to provide comprehensive, well-sourced answers to
complex queries.
"""

from .agent import deep_research_agent, deep_research_agent_tool
from .shared import (
    AgentTask,
    AgentResult,
    ResearchWorkflow,
    WorkflowStorage,
    MessageBus,
    ResearchWorkflowCoordinator,
)

__all__ = [
    "deep_research_agent",
    "deep_research_agent_tool",
    "AgentTask",
    "AgentResult",
    "ResearchWorkflow",
    "WorkflowStorage",
    "MessageBus",
    "ResearchWorkflowCoordinator",
]
