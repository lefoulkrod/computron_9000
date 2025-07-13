"""Shared type definitions for the multi-agent research workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AgentTask(BaseModel):
    """Represents a task assigned to a specific agent."""

    task_id: str
    agent_type: (
        str  # query_decomposition, web_research, social_research, analysis, synthesis
    )
    task_type: str  # decompose_query, search_web, analyze_sources, synthesize_findings
    input_data: dict[str, Any]
    priority: int = 5
    dependencies: list[str] = []
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: str
    assigned_at: str | None = None
    completed_at: str | None = None


class AgentResult(BaseModel):
    """Represents the result from an agent task."""

    task_id: str
    agent_type: str
    result_data: dict[str, Any]
    success: bool
    error_message: str | None = None
    sources_used: list[str] = []
    follow_up_tasks: list[AgentTask] = []
    completion_time: str


class ResearchWorkflow(BaseModel):
    """Represents the overall research workflow state."""

    workflow_id: str
    original_query: str
    current_phase: str  # decomposition, research, analysis, synthesis
    active_tasks: list[AgentTask] = []
    completed_tasks: list[AgentResult] = []
    workflow_state: dict[str, Any] = {}
    source_tracking_enabled: bool = True
    source_registry_id: str | None = None  # Links to SharedSourceRegistry
    created_at: str
    updated_at: str


class SubQuery(BaseModel):
    """Represents a sub-query generated from decomposing a complex query."""

    query_id: str
    query_text: str
    description: str
    importance: int = 5  # 1-10 scale
    estimated_complexity: int = 3  # 1-5 scale
    suggested_sources: list[str] = []  # web, social, academic, news
    research_type: str = "factual"  # factual, analytical, comparative, opinion
    context_requirements: list[str] = []
    created_at: str


class QueryDependency(BaseModel):
    """Represents a dependency relationship between sub-queries."""

    dependent_query_id: str
    prerequisite_query_id: str
    dependency_type: str = "sequential"  # sequential, informational, contextual
    dependency_strength: int = 5  # 1-10 scale
    description: str


class ResearchStrategy(BaseModel):
    """Represents a comprehensive research strategy for a decomposed query."""

    strategy_id: str
    original_query: str
    sub_queries: list[SubQuery]
    dependencies: list[QueryDependency]
    execution_order: list[str]  # List of query_ids in execution order
    estimated_duration: int  # minutes
    success_criteria: list[str]
    potential_challenges: list[str]
    created_at: str


class CredibilityAssessment(BaseModel):
    """Represents a credibility assessment of a source."""

    url: str
    domain_credibility: float  # 0.0 to 1.0
    content_quality: float  # 0.0 to 1.0
    authoritativeness: float  # 0.0 to 1.0
    bias_indicators: list[str] = []
    credibility_factors: list[str] = []
    overall_score: float  # 0.0 to 1.0
    recommendation: str  # high, medium, low, unreliable
    assessment_details: dict[str, Any] = {}


class SourceCategorization(BaseModel):
    """Represents the categorization of a source."""

    url: str
    primary_category: str  # academic, government, news, commercial, etc.
    secondary_categories: list[str] = []
    confidence: float  # 0.0 to 1.0
    reasoning: str
    indicators: list[str] = []


class WebpageMetadata(BaseModel):
    """Represents extracted metadata from a webpage."""

    url: str
    title: str | None = None
    author: str | None = None
    publication_date: str | None = None
    last_modified: str | None = None
    description: str | None = None
    keywords: list[str] = []
    language: str | None = None
    content_type: str | None = None
    word_count: int | None = None
    extracted_at: str


class ResearchSource(BaseModel):
    """Represents a research source with tracking information."""

    url: str
    source_type: str = "web"  # web, reddit, academic, etc.
    title: str | None = None
    description: str | None = None
    content_summary: str | None = None  # For backward compatibility with tests
    access_count: int = 0
    first_accessed: str | None = None
    last_accessed: str | None = None
    tools_used: list[str] = []
    metadata: dict[str, Any] = {}


class ResearchCitation(BaseModel):
    """Represents a research citation."""

    source: ResearchSource
    citation_text: str
    citation_style: str = "apa"  # apa, mla, chicago
    page_accessed: str | None = None
    relevance_score: float = 0.0
