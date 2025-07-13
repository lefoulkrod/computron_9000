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
