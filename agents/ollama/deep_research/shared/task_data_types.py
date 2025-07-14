"""Task data types for the enhanced task system.

This module defines Pydantic models for structured task data that enable
coordinated multi-agent research workflows with type safety and validation.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BaseTaskData(BaseModel):
    """Base class for all task data types with common fields."""

    task_id: str = Field(..., description="Unique identifier for the task")
    workflow_id: str = Field(..., description="Identifier for the parent workflow")
    agent_type: str = Field(..., description="Type of agent this task is assigned to")
    created_at: str = Field(..., description="ISO timestamp when task was created")

    class Config:
        """Pydantic configuration."""

        json_encoders: dict[type, type] = {
            # Custom JSON encoders if needed
        }


class WebResearchTaskData(BaseTaskData):
    """Task data for web research agents."""

    agent_type: str = Field(
        default="web_research", description="Agent type for web research"
    )

    # Core research parameters
    search_query: str = Field(..., description="Primary search query to research")
    search_domains: list[str] = Field(
        default_factory=list,
        description="Specific domains to focus on (e.g., academic, news, government)",
    )
    max_sources: int = Field(
        default=10, description="Maximum number of sources to collect"
    )

    # Search configuration
    search_depth: str = Field(
        default="comprehensive",
        description="Search depth: 'quick', 'standard', or 'comprehensive'",
    )
    include_recent_only: bool = Field(
        default=False, description="Whether to focus only on recent content"
    )
    content_types: list[str] = Field(
        default_factory=lambda: ["articles", "reports", "studies"],
        description="Types of content to prioritize",
    )

    # Context from workflow
    related_queries: list[str] = Field(
        default_factory=list, description="Related subqueries from query decomposition"
    )
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class SocialResearchTaskData(BaseTaskData):
    """Task data for social research agents."""

    agent_type: str = Field(
        default="social_research", description="Agent type for social research"
    )

    # Core research parameters
    search_query: str = Field(
        ..., description="Primary query for social media research"
    )
    platforms: list[str] = Field(
        default_factory=lambda: ["reddit"],
        description="Social platforms to search (currently supports reddit)",
    )
    max_posts: int = Field(default=20, description="Maximum number of posts to analyze")

    # Search configuration
    sort_by: str = Field(
        default="relevance", description="Sort order: 'relevance', 'recent', or 'top'"
    )
    include_comments: bool = Field(
        default=True, description="Whether to include comment analysis"
    )
    sentiment_analysis: bool = Field(
        default=True, description="Whether to perform sentiment analysis"
    )

    # Subreddit targeting
    target_subreddits: list[str] = Field(
        default_factory=list,
        description="Specific subreddits to focus on (empty for general search)",
    )

    # Context from workflow
    related_queries: list[str] = Field(
        default_factory=list, description="Related subqueries from query decomposition"
    )
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class AnalysisTaskData(BaseTaskData):
    """Task data for analysis agents."""

    agent_type: str = Field(default="analysis", description="Agent type for analysis")

    # Analysis focus
    analysis_type: str = Field(
        default="comprehensive",
        description="Type of analysis: 'comprehensive', 'comparative', or 'focused'",
    )
    analysis_questions: list[str] = Field(
        default_factory=list, description="Specific questions to address in analysis"
    )

    # Source data for analysis
    research_results: dict[str, Any] = Field(
        default_factory=dict, description="Results from web and social research agents"
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about sources for credibility assessment",
    )

    # Analysis configuration
    cross_verification: bool = Field(
        default=True, description="Whether to perform cross-source verification"
    )
    bias_detection: bool = Field(
        default=True, description="Whether to analyze for potential bias"
    )
    confidence_scoring: bool = Field(
        default=True, description="Whether to provide confidence scores for findings"
    )

    # Context from workflow
    original_query: str = Field(..., description="Original research query")
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class SynthesisTaskData(BaseTaskData):
    """Task data for synthesis agents."""

    agent_type: str = Field(default="synthesis", description="Agent type for synthesis")

    # Synthesis goals
    output_format: str = Field(
        default="comprehensive_report",
        description="Desired output format: 'comprehensive_report', 'summary', or 'executive_brief'",
    )
    target_audience: str = Field(
        default="general",
        description="Target audience: 'general', 'academic', 'technical', or 'executive'",
    )
    synthesis_focus: list[str] = Field(
        default_factory=list, description="Key aspects to emphasize in synthesis"
    )

    # Input data for synthesis
    analysis_results: dict[str, Any] = Field(
        default_factory=dict, description="Results from analysis agents"
    )
    research_findings: dict[str, Any] = Field(
        default_factory=dict, description="Raw research findings from all agents"
    )

    # Synthesis configuration
    include_citations: bool = Field(
        default=True, description="Whether to include detailed citations"
    )
    confidence_indicators: bool = Field(
        default=True,
        description="Whether to include confidence indicators for findings",
    )
    executive_summary: bool = Field(
        default=True, description="Whether to include an executive summary"
    )

    # Context from workflow
    original_query: str = Field(..., description="Original research query")
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class QueryDecompositionTaskData(BaseTaskData):
    """Task data for query decomposition agents."""

    agent_type: str = Field(
        default="query_decomposition", description="Agent type for query decomposition"
    )

    # Decomposition parameters
    original_query: str = Field(..., description="Original complex query to decompose")
    max_subqueries: int = Field(
        default=5, description="Maximum number of subqueries to create"
    )
    decomposition_strategy: str = Field(
        default="comprehensive",
        description="Strategy: 'comprehensive', 'focused', or 'exploratory'",
    )

    # Research domain preferences
    preferred_domains: list[str] = Field(
        default_factory=lambda: ["web", "social"],
        description="Preferred research domains for subqueries",
    )
    domain_balance: str = Field(
        default="balanced",
        description="How to balance domains: 'balanced', 'web_heavy', or 'social_heavy'",
    )

    # Decomposition configuration
    include_context_queries: bool = Field(
        default=True, description="Whether to include background/context subqueries"
    )
    prioritize_current_events: bool = Field(
        default=False, description="Whether to prioritize recent/current event aspects"
    )

    # Workflow context
    research_goals: list[str] = Field(
        default_factory=list, description="High-level goals for the research"
    )
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for decomposition strategy",
    )


# Type mapping for convenience
TASK_DATA_TYPES = {
    "web_research": WebResearchTaskData,
    "social_research": SocialResearchTaskData,
    "analysis": AnalysisTaskData,
    "synthesis": SynthesisTaskData,
    "query_decomposition": QueryDecompositionTaskData,
}


def create_task_data(agent_type: str, **kwargs: Any) -> BaseTaskData:
    """Create a task data instance for the specified agent type.

    Args:
        agent_type: Type of agent (web_research, social_research, etc.)
        **kwargs: Task data fields

    Returns:
        Task data instance of the appropriate type.

    Raises:
        ValueError: If agent_type is not supported.
    """
    if agent_type not in TASK_DATA_TYPES:
        raise ValueError(f"Unsupported agent type: {agent_type}")

    task_data_class = TASK_DATA_TYPES[agent_type]
    # Explicit cast for mypy since TASK_DATA_TYPES values are type[BaseTaskData]
    result: BaseTaskData = task_data_class(agent_type=agent_type, **kwargs)
    return result


def validate_task_data(task_data: dict[str, Any], agent_type: str) -> BaseTaskData:
    """Validate task data dictionary against the appropriate schema.

    Args:
        task_data: Task data dictionary to validate
        agent_type: Expected agent type

    Returns:
        Validated task data instance.

    Raises:
        ValueError: If validation fails or agent_type is not supported.
    """
    if agent_type not in TASK_DATA_TYPES:
        raise ValueError(f"Unsupported agent type: {agent_type}")

    task_data_class = TASK_DATA_TYPES[agent_type]
    try:
        # Explicit cast for mypy since TASK_DATA_TYPES values are type[BaseTaskData]
        result: BaseTaskData = task_data_class(**task_data)
        return result
    except Exception as e:
        logger.error(f"Task data validation failed for {agent_type}: {e}")
        raise ValueError(f"Invalid task data for {agent_type}: {e}") from e
