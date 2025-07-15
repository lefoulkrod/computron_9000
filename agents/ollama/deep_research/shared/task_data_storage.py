"""Task data storage for the enhanced task system.

This module provides in-memory storage for task data with thread safety
and access control for the multi-agent research workflow.
"""

import logging
import threading
from typing import Any, Optional

from .task_data_types import BaseTaskData

logger = logging.getLogger(__name__)


class TaskDataStorage:
    """Thread-safe in-memory storage for task data.

    This singleton class manages task data storage with proper access control:
    - Only coordinators can create and delete tasks
    - All agents can retrieve their assigned task data
    - Thread-safe operations with proper error handling
    """

    _instance: Optional["TaskDataStorage"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskDataStorage":
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize storage if not already initialized."""
        if not getattr(self, "_initialized", False):
            self._task_data: dict[str, BaseTaskData] = {}
            self._storage_lock = threading.RLock()
            self._initialized = True
            logger.info("Task data storage initialized")

    def store_task_data(self, task_data: BaseTaskData) -> None:
        """Store task data (coordinator only).

        Args:
            task_data: Task data instance to store

        Raises:
            ValueError: If task_id already exists
            TypeError: If task_data is not a BaseTaskData instance

        """
        if not isinstance(task_data, BaseTaskData):
            raise TypeError("task_data must be a BaseTaskData instance")

        # Log the entire task data object for debugging
        logger.debug(f"Storing task data: {task_data}")

        with self._storage_lock:
            if task_data.task_id in self._task_data:
                raise ValueError(f"Task ID {task_data.task_id} already exists")

            self._task_data[task_data.task_id] = task_data
            logger.info(
                f"Stored task data for task {task_data.task_id} "
                f"(agent: {task_data.agent_type}, workflow: {task_data.workflow_id})",
            )

    def retrieve_task_data(self, task_id: str) -> BaseTaskData:
        """Retrieve task data by task ID.

        Args:
            task_id: Unique task identifier

        Returns:
            Task data instance for the specified task

        Raises:
            KeyError: If task_id is not found
            ValueError: If task_id is empty

        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        logger.debug(f"Attempting to retrieve task data for task_id: {task_id}")

        with self._storage_lock:
            if task_id not in self._task_data:
                logger.error(f"Task ID {task_id} not found in storage")
                raise KeyError(f"Task ID {task_id} not found")

            task_data = self._task_data[task_id]

            # Log the entire task data object for debugging
            logger.debug(f"Retrieved task data for task {task_id}: {task_data}")

            return task_data

    def delete_task_data(self, task_id: str) -> bool:
        """Delete task data (coordinator only).

        Args:
            task_id: Unique task identifier to delete

        Returns:
            True if task was deleted, False if task was not found

        Raises:
            ValueError: If task_id is empty

        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        with self._storage_lock:
            if task_id in self._task_data:
                task_data = self._task_data.pop(task_id)
                logger.info(
                    f"Deleted task data for task {task_id} "
                    f"(agent: {task_data.agent_type})",
                )
                return True
            logger.warning(f"Attempted to delete non-existent task {task_id}")
            return False

    def list_task_ids(self, workflow_id: str | None = None) -> list[str]:
        """List all task IDs, optionally filtered by workflow.

        Args:
            workflow_id: Optional workflow ID to filter by

        Returns:
            List of task IDs

        """
        with self._storage_lock:
            if workflow_id is None:
                return list(self._task_data.keys())
            return [
                task_id
                for task_id, task_data in self._task_data.items()
                if task_data.workflow_id == workflow_id
            ]

    def get_task_count(self, workflow_id: str | None = None) -> int:
        """Get count of stored tasks, optionally filtered by workflow.

        Args:
            workflow_id: Optional workflow ID to filter by

        Returns:
            Number of stored tasks

        """
        with self._storage_lock:
            if workflow_id is None:
                return len(self._task_data)
            return sum(
                1
                for task_data in self._task_data.values()
                if task_data.workflow_id == workflow_id
            )

    def clear_workflow_tasks(self, workflow_id: str) -> int:
        """Clear all tasks for a specific workflow (coordinator only).

        Args:
            workflow_id: Workflow ID to clear tasks for

        Returns:
            Number of tasks cleared

        Raises:
            ValueError: If workflow_id is empty

        """
        if not workflow_id or not workflow_id.strip():
            raise ValueError("workflow_id cannot be empty")

        with self._storage_lock:
            tasks_to_remove = [
                task_id
                for task_id, task_data in self._task_data.items()
                if task_data.workflow_id == workflow_id
            ]

            for task_id in tasks_to_remove:
                del self._task_data[task_id]

            count = len(tasks_to_remove)
            if count > 0:
                logger.info(f"Cleared {count} tasks for workflow {workflow_id}")

            return count

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics for monitoring.

        Returns:
            Dictionary with storage statistics

        """
        with self._storage_lock:
            stats: dict[str, Any] = {
                "total_tasks": len(self._task_data),
                "tasks_by_agent_type": {},
                "tasks_by_workflow": {},
            }

            for task_data in self._task_data.values():
                # Count by agent type
                agent_type = task_data.agent_type
                agent_stats = stats["tasks_by_agent_type"]
                assert isinstance(agent_stats, dict)
                current_count = agent_stats.get(agent_type, 0)
                agent_stats[agent_type] = current_count + 1

                # Count by workflow
                workflow_id = task_data.workflow_id
                workflow_stats = stats["tasks_by_workflow"]
                assert isinstance(workflow_stats, dict)
                current_count = workflow_stats.get(workflow_id, 0)
                workflow_stats[workflow_id] = current_count + 1

            return stats


# Global storage instance
_storage_instance: TaskDataStorage | None = None


def get_task_data_storage() -> TaskDataStorage:
    """Get the global task data storage instance.

    Returns:
        TaskDataStorage singleton instance

    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = TaskDataStorage()
    return _storage_instance


def store_task_data(task_data: BaseTaskData) -> None:
    """Store task data using the global storage instance.

    Args:
        task_data: Task data instance to store

    """
    storage = get_task_data_storage()
    storage.store_task_data(task_data)


def retrieve_task_data(task_id: str) -> BaseTaskData:
    """Retrieve task data using the global storage instance.

    Args:
        task_id: Unique task identifier

    Returns:
        Task data instance for the specified task

    """
    storage = get_task_data_storage()
    return storage.retrieve_task_data(task_id)


def delete_task_data(task_id: str) -> bool:
    """Delete task data using the global storage instance.

    Args:
        task_id: Unique task identifier to delete

    Returns:
        True if task was deleted, False if task was not found

    """
    storage = get_task_data_storage()
    return storage.delete_task_data(task_id)


def clear_workflow_tasks(workflow_id: str) -> int:
    """Clear all tasks for a workflow using the global storage instance.

    Args:
        workflow_id: Workflow ID to clear tasks for

    Returns:
        Number of tasks cleared

    """
    storage = get_task_data_storage()
    return storage.clear_workflow_tasks(workflow_id)
