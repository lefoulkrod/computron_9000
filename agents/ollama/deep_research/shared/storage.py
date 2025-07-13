"""Simple in-memory storage backend for research workflows."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .types import ResearchWorkflow

logger = logging.getLogger(__name__)


class WorkflowStorage:
    """In-memory storage for :class:`ResearchWorkflow` objects."""

    def __init__(self) -> None:
        self._workflows: Dict[str, ResearchWorkflow] = {}

    def create_workflow(self, workflow: ResearchWorkflow) -> None:
        logger.debug("Creating workflow %s", workflow.workflow_id)
        self._workflows[workflow.workflow_id] = workflow

    def get_workflow(self, workflow_id: str) -> Optional[ResearchWorkflow]:
        return self._workflows.get(workflow_id)

    def update_workflow(self, workflow: ResearchWorkflow) -> None:
        logger.debug("Updating workflow %s", workflow.workflow_id)
        self._workflows[workflow.workflow_id] = workflow

    def delete_workflow(self, workflow_id: str) -> None:
        logger.debug("Deleting workflow %s", workflow_id)
        self._workflows.pop(workflow_id, None)
