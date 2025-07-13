"""Enhanced storage backend for research workflows with source tracking persistence."""

from __future__ import annotations

import json
import logging
from typing import Any

from .source_tracking import SharedSourceRegistry
from .types import ResearchWorkflow

logger = logging.getLogger(__name__)


class WorkflowStorage:
    """Enhanced storage for :class:`ResearchWorkflow` objects with source tracking persistence."""

    def __init__(self) -> None:
        self._workflows: dict[str, ResearchWorkflow] = {}
        self._source_registries: dict[str, SharedSourceRegistry] = {}  # workflow_id -> registry

    def create_workflow(self, workflow: ResearchWorkflow) -> None:
        """
        Create a new workflow and initialize its source registry.

        Args:
            workflow (ResearchWorkflow): The workflow to create.
        """
        logger.debug("Creating workflow %s", workflow.workflow_id)
        self._workflows[workflow.workflow_id] = workflow
        self._source_registries[workflow.workflow_id] = SharedSourceRegistry()

    def get_workflow(self, workflow_id: str) -> ResearchWorkflow | None:
        """
        Get a workflow by ID.

        Args:
            workflow_id (str): The workflow ID.

        Returns:
            Optional[ResearchWorkflow]: The workflow if found, None otherwise.
        """
        return self._workflows.get(workflow_id)

    def get_source_registry(self, workflow_id: str) -> SharedSourceRegistry | None:
        """
        Get the source registry for a workflow.

        Args:
            workflow_id (str): The workflow ID.

        Returns:
            Optional[SharedSourceRegistry]: The source registry if found, None otherwise.
        """
        return self._source_registries.get(workflow_id)

    def update_workflow(self, workflow: ResearchWorkflow) -> None:
        """
        Update an existing workflow.

        Args:
            workflow (ResearchWorkflow): The updated workflow.
        """
        logger.debug("Updating workflow %s", workflow.workflow_id)
        self._workflows[workflow.workflow_id] = workflow

    def delete_workflow(self, workflow_id: str) -> None:
        """
        Delete a workflow and its associated source registry.

        Args:
            workflow_id (str): The workflow ID to delete.
        """
        logger.debug("Deleting workflow %s", workflow_id)
        self._workflows.pop(workflow_id, None)
        self._source_registries.pop(workflow_id, None)

    def save_workflow_to_file(self, workflow_id: str, filepath: str) -> None:
        """
        Save a workflow and its source registry to a JSON file.

        Args:
            workflow_id (str): The workflow ID to save.
            filepath (str): The file path to save to.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.get_workflow(workflow_id)
        source_registry = self.get_source_registry(workflow_id)

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        data = {
            "workflow": workflow.model_dump(),
            "source_registry": source_registry.to_dict() if source_registry else {},
            "version": "1.0",
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved workflow {workflow_id} to {filepath}")

    def load_workflow_from_file(self, filepath: str) -> str:
        """
        Load a workflow and its source registry from a JSON file.

        Args:
            filepath (str): The file path to load from.

        Returns:
            str: The workflow ID of the loaded workflow.

        Raises:
            ValueError: If file format is invalid.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "workflow" not in data:
            raise ValueError("Invalid workflow file format: missing 'workflow' key")

        workflow = ResearchWorkflow.model_validate(data["workflow"])
        self._workflows[workflow.workflow_id] = workflow

        # Load source registry if present
        if "source_registry" in data and data["source_registry"]:
            source_registry = SharedSourceRegistry.from_dict(data["source_registry"])
            self._source_registries[workflow.workflow_id] = source_registry
        else:
            self._source_registries[workflow.workflow_id] = SharedSourceRegistry()

        logger.info(f"Loaded workflow {workflow.workflow_id} from {filepath}")
        return workflow.workflow_id

    def export_workflow_data(self, workflow_id: str) -> dict[str, Any]:
        """
        Export workflow and source registry data as a dictionary.

        Args:
            workflow_id (str): The workflow ID to export.

        Returns:
            dict: Dictionary containing workflow and source registry data.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.get_workflow(workflow_id)
        source_registry = self.get_source_registry(workflow_id)

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        return {
            "workflow": workflow.model_dump(),
            "source_registry": source_registry.to_dict() if source_registry else {},
            "export_timestamp": workflow.updated_at,
            "version": "1.0",
        }

    def import_workflow_data(self, data: dict[str, Any]) -> str:
        """
        Import workflow and source registry data from a dictionary.

        Args:
            data (dict): Dictionary containing workflow and source registry data.

        Returns:
            str: The workflow ID of the imported workflow.

        Raises:
            ValueError: If data format is invalid.
        """
        if "workflow" not in data:
            raise ValueError("Invalid data format: missing 'workflow' key")

        workflow = ResearchWorkflow.model_validate(data["workflow"])
        self._workflows[workflow.workflow_id] = workflow

        # Import source registry if present
        if "source_registry" in data and data["source_registry"]:
            source_registry = SharedSourceRegistry.from_dict(data["source_registry"])
            self._source_registries[workflow.workflow_id] = source_registry
        else:
            self._source_registries[workflow.workflow_id] = SharedSourceRegistry()

        logger.info(f"Imported workflow {workflow.workflow_id}")
        return workflow.workflow_id

    def list_workflows(self) -> list[str]:
        """
        List all workflow IDs in storage.

        Returns:
            list[str]: List of workflow IDs.
        """
        return list(self._workflows.keys())

    def get_workflow_summary(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Get a summary of a workflow including source tracking stats.

        Args:
            workflow_id (str): The workflow ID.

        Returns:
            Optional[dict]: Summary data if workflow found, None otherwise.
        """
        workflow = self.get_workflow(workflow_id)
        source_registry = self.get_source_registry(workflow_id)

        if not workflow:
            return None

        summary = {
            "workflow_id": workflow.workflow_id,
            "original_query": workflow.original_query,
            "current_phase": workflow.current_phase,
            "active_tasks": len(workflow.active_tasks),
            "completed_tasks": len(workflow.completed_tasks),
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
        }

        if source_registry:
            summary.update({
                "total_sources": len(source_registry.get_all_sources()),
                "total_accesses": len(source_registry.get_all_accesses()),
                "active_agents": len(set(access.agent_id for access in source_registry.get_all_accesses())),
            })

        return summary

    def clear_all(self) -> None:
        """Clear all workflows and source registries."""
        self._workflows.clear()
        self._source_registries.clear()
        logger.info("Cleared all workflow storage")


# Global storage instance for the module
_storage_instance: WorkflowStorage | None = None


def get_storage() -> WorkflowStorage:
    """
    Get the global storage instance (singleton pattern).

    Returns:
        WorkflowStorage: The global storage instance.
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = WorkflowStorage()
    return _storage_instance


# Module exports
__all__ = [
    "WorkflowStorage",
    "get_storage",
]
