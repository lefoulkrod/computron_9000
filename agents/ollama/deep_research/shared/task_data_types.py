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
    """Base class for all task data types with common fields.

    This class serves as the foundation for all task data models in the system,
    providing common fields that are required across all task types. All specialized
    task data classes inherit from this base class.

    Attributes:
        task_id: Unique identifier for the task.
        workflow_id: Identifier for the parent research workflow.
        agent_type: Type of agent this task is assigned to (e.g., "web_research").
        created_at: ISO 8601 timestamp string indicating when the task was created.

    """

    task_id: str = Field(..., description="Unique identifier for the task")
    workflow_id: str = Field(..., description="Identifier for the parent workflow")
    agent_type: str = Field(..., description="Type of agent this task is assigned to")
    created_at: str = Field(..., description="ISO timestamp when task was created")

    class Config:
        """Pydantic configuration for BaseTaskData.

        This inner class configures Pydantic behavior for all task data models,
        including custom JSON encoders and other model-wide settings.

        Attributes:
            json_encoders: Dictionary mapping types to custom JSON encoder functions.

        """

        json_encoders: dict[type, type] = {
            # Custom JSON encoders if needed
        }


class WebResearchTaskData(BaseTaskData):
    """Task data for web research agents.

    This class defines the configuration and parameters for web research tasks.
    It includes search parameters, content filtering options, and context from
    the broader research workflow.

    Attributes:
        agent_type: Fixed as "web_research" for this task type.
        search_query: The primary query string for web research.
        search_domains: List of specific domains to prioritize in search results.
        max_sources: Maximum number of sources to collect and analyze.
        search_depth: Controls search thoroughness ("quick", "standard", "comprehensive").
        include_recent_only: Whether to limit results to recent content.
        content_types: Types of content to prioritize (e.g., articles, reports).
        related_queries: Additional related queries from decomposition.
        workflow_context: Additional contextual information for the task.

    """

    agent_type: str = Field(
        default="web_research",
        description="Agent type for web research",
    )

    # Core research parameters
    search_query: str = Field(..., description="Primary search query to research")
    search_domains: list[str] = Field(
        default_factory=list,
        description="Specific domains to focus on (e.g., academic, news, government)",
    )
    max_sources: int = Field(
        default=10,
        description="Maximum number of sources to collect",
    )

    # Search configuration
    search_depth: str = Field(
        default="comprehensive",
        description="Search depth: 'quick', 'standard', or 'comprehensive'",
    )
    include_recent_only: bool = Field(
        default=False,
        description="Whether to focus only on recent content",
    )
    content_types: list[str] = Field(
        default_factory=lambda: ["articles", "reports", "studies"],
        description="Types of content to prioritize",
    )

    # Context from workflow
    related_queries: list[str] = Field(
        default_factory=list,
        description="Related subqueries from query decomposition",
    )
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class SocialResearchTaskData(BaseTaskData):
    """Task data for social research agents.

    This class defines the configuration and parameters for social media research tasks.
    It includes parameters for targeting specific platforms, filtering content,
    and analyzing social media discussions.

    Attributes:
        agent_type: Fixed as "social_research" for this task type.
        search_query: The primary query string for social media research.
        platforms: List of social platforms to search (currently supports reddit).
        max_posts: Maximum number of posts to retrieve and analyze.
        sort_by: How to sort results ("relevance", "recent", or "top").
        include_comments: Whether to analyze comment threads.
        sentiment_analysis: Whether to perform sentiment analysis on content.
        target_subreddits: Specific subreddits to focus on if using Reddit.
        related_queries: Additional related queries from decomposition.
        workflow_context: Additional contextual information for the task.

    """

    agent_type: str = Field(
        default="social_research",
        description="Agent type for social research",
    )

    # Core research parameters
    search_query: str = Field(
        ...,
        description="Primary query for social media research",
    )
    platforms: list[str] = Field(
        default_factory=lambda: ["reddit"],
        description="Social platforms to search (currently supports reddit)",
    )
    max_posts: int = Field(default=20, description="Maximum number of posts to analyze")

    # Search configuration
    sort_by: str = Field(
        default="relevance",
        description="Sort order: 'relevance', 'recent', or 'top'",
    )
    include_comments: bool = Field(
        default=True,
        description="Whether to include comment analysis",
    )
    sentiment_analysis: bool = Field(
        default=True,
        description="Whether to perform sentiment analysis",
    )

    # Subreddit targeting
    target_subreddits: list[str] = Field(
        default_factory=list,
        description="Specific subreddits to focus on (empty for general search)",
    )

    # Context from workflow
    related_queries: list[str] = Field(
        default_factory=list,
        description="Related subqueries from query decomposition",
    )
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class AnalysisTaskData(BaseTaskData):
    """Task data for analysis agents.

    This class defines the configuration and parameters for analysis tasks.
    It includes settings for the type of analysis to perform, specific questions
    to address, and options for cross-verification and confidence scoring.

    Attributes:
        agent_type: Fixed as "analysis" for this task type.
        analysis_type: Analysis strategy ("comprehensive", "comparative", "focused").
        analysis_questions: Specific questions to address during analysis.
        research_results: Results from web and social research for analysis.
        source_metadata: Metadata about sources for credibility assessment.
        cross_verification: Whether to perform cross-source verification.
        bias_detection: Whether to analyze for potential bias in sources.
        confidence_scoring: Whether to provide confidence scores for findings.
        original_query: The original research query being addressed.
        workflow_context: Additional contextual information for the task.

    """

    agent_type: str = Field(default="analysis", description="Agent type for analysis")

    # Analysis focus
    analysis_type: str = Field(
        default="comprehensive",
        description="Type of analysis: 'comprehensive', 'comparative', or 'focused'",
    )
    analysis_questions: list[str] = Field(
        default_factory=list,
        description="Specific questions to address in analysis",
    )

    # Source data for analysis
    research_results: dict[str, Any] = Field(
        default_factory=dict,
        description="Results from web and social research agents",
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about sources for credibility assessment",
    )

    # Analysis configuration
    cross_verification: bool = Field(
        default=True,
        description="Whether to perform cross-source verification",
    )
    bias_detection: bool = Field(
        default=True,
        description="Whether to analyze for potential bias",
    )
    confidence_scoring: bool = Field(
        default=True,
        description="Whether to provide confidence scores for findings",
    )

    # Context from workflow
    original_query: str = Field(..., description="Original research query")
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class SynthesisTaskData(BaseTaskData):
    """Task data for synthesis agents.

    This class defines the configuration and parameters for synthesis tasks.
    It includes settings for output formats, target audiences, and synthesis
    of research findings into coherent reports or summaries.

    Attributes:
        agent_type: Fixed as "synthesis" for this task type.
        output_format: Format of output ("comprehensive_report", "summary", "executive_brief").
        target_audience: Intended audience ("general", "academic", "technical", "executive").
        synthesis_focus: Key aspects or themes to emphasize.
        analysis_results: Results from analysis agents to synthesize.
        research_findings: Raw research findings from all agents.
        include_citations: Whether to include detailed source citations.
        confidence_indicators: Whether to indicate confidence levels for findings.
        executive_summary: Whether to include an executive summary.
        original_query: The original research query being addressed.
        workflow_context: Additional contextual information for the task.

    """

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
        default_factory=list,
        description="Key aspects to emphasize in synthesis",
    )

    # Input data for synthesis
    analysis_results: dict[str, Any] = Field(
        default_factory=dict,
        description="Results from analysis agents",
    )
    research_findings: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw research findings from all agents",
    )

    # Synthesis configuration
    include_citations: bool = Field(
        default=True,
        description="Whether to include detailed citations",
    )
    confidence_indicators: bool = Field(
        default=True,
        description="Whether to include confidence indicators for findings",
    )
    executive_summary: bool = Field(
        default=True,
        description="Whether to include an executive summary",
    )

    # Context from workflow
    original_query: str = Field(..., description="Original research query")
    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context from the broader research workflow",
    )


class QueryDecompositionTaskData(BaseTaskData):
    """Task data for query decomposition agents.

    This class defines the configuration and parameters for query decomposition tasks.
    It includes settings for breaking down complex research queries into
    manageable sub-queries with appropriate research strategies.

    Attributes:
        agent_type: Fixed as "query_decomposition" for this task type.
        original_query: The original complex query to be decomposed.
        max_subqueries: Maximum number of subqueries to generate.
        decomposition_strategy: Approach to use ("comprehensive", "focused", "exploratory").
        preferred_domains: Research domains to target ("web", "social", etc.).
        domain_balance: Balance between domains ("balanced", "web_heavy", "social_heavy").
        include_context_queries: Whether to include background/contextual subqueries.
        prioritize_current_events: Whether to emphasize recent developments.
        research_goals: High-level goals for the overall research.
        workflow_context: Additional contextual information for the task.

    """

    agent_type: str = Field(
        default="query_decomposition",
        description="Agent type for query decomposition",
    )

    # Decomposition parameters
    original_query: str = Field(..., description="Original complex query to decompose")
    max_subqueries: int = Field(
        default=5,
        description="Maximum number of subqueries to create",
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
        default=True,
        description="Whether to include background/context subqueries",
    )
    prioritize_current_events: bool = Field(
        default=False,
        description="Whether to prioritize recent/current event aspects",
    )

    # Workflow context
    research_goals: list[str] = Field(
        default_factory=list,
        description="High-level goals for the research",
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

    This function creates and returns a new task data instance of the appropriate
    type based on the specified agent_type. It ensures that the correct Pydantic
    model is used for the task data and applies any provided field values.

    Args:
        agent_type: Type of agent (web_research, social_research, etc.)
        **kwargs: Task data fields to set on the created instance

    Returns:
        BaseTaskData: A task data instance of the appropriate type with the specified fields.

    Raises:
        ValueError: If agent_type is not supported or recognized.

    """
    if agent_type not in TASK_DATA_TYPES:
        raise ValueError(f"Unsupported agent type: {agent_type}")

    task_data_class = TASK_DATA_TYPES[agent_type]
    # Explicit cast for mypy since TASK_DATA_TYPES values are type[BaseTaskData]
    result: BaseTaskData = task_data_class(agent_type=agent_type, **kwargs)
    return result


def validate_task_data(task_data: dict[str, Any], agent_type: str) -> BaseTaskData:
    """Validate task data dictionary against the appropriate schema.

    This function validates a dictionary of task data against the Pydantic model
    for the specified agent type. It ensures that all required fields are present
    and that the data conforms to the expected types and constraints.

    Args:
        task_data: Dictionary containing task data to validate
        agent_type: Expected agent type, determines which model to use for validation

    Returns:
        BaseTaskData: A validated task data instance of the appropriate type.

    Raises:
        ValueError: If validation fails (missing fields, wrong types) or if agent_type
            is not supported.

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
