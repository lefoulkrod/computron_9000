"""Shared type definitions for the multi-agent research workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AgentTask(BaseModel):
    """Represents a task assigned to a specific agent."""

    task_id: str
    agent_type: str  # query_decomposition, web_research, social_research, analysis, synthesis
    task_type: str  # decompose_query, search_web, analyze_sources, synthesize_findings
    input_data: Dict[str, Any]
    priority: int = 5
    dependencies: List[str] = []
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: str
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None


class AgentResult(BaseModel):
    """Represents the result from an agent task."""

    task_id: str
    agent_type: str
    result_data: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    sources_used: List[str] = []
    follow_up_tasks: List[AgentTask] = []
    completion_time: str


class ResearchWorkflow(BaseModel):
    """Represents the overall research workflow state."""

    workflow_id: str
    original_query: str
    current_phase: str  # decomposition, research, analysis, synthesis
    active_tasks: List[AgentTask] = []
    completed_tasks: List[AgentResult] = []
    workflow_state: Dict[str, Any] = {}
    created_at: str
    updated_at: str
