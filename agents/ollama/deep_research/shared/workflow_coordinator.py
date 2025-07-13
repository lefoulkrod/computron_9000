"""Base classes for coordinating the multi-agent research workflow."""

from __future__ import annotations

import logging
from typing import Any

from .communication import MessageBus
from .storage import WorkflowStorage
from .types import AgentResult, AgentTask

logger = logging.getLogger(__name__)


class ResearchWorkflowCoordinator:
    """Coordinates multi-agent research workflow."""

    def __init__(self, storage: WorkflowStorage, bus: MessageBus) -> None:
        self._storage = storage
        self._bus = bus

    async def start_research_workflow(self, query: str) -> str:
        """Initiate a new research workflow."""
        raise NotImplementedError

    async def assign_task_to_agent(self, task: AgentTask) -> str:
        """Assign a task to the appropriate specialized agent."""
        raise NotImplementedError

    async def process_agent_result(self, result: AgentResult) -> list[AgentTask]:
        """Process results from an agent and generate follow-up tasks."""
        raise NotImplementedError

    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any]:
        """Get current status of a research workflow."""
        raise NotImplementedError
