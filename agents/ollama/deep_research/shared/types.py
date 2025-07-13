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
    created_at: str
    updated_at: str
