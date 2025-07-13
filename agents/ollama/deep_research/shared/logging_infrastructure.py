"""
Logging and error handling infrastructure for multi-agent system.

This module provides centralized logging configuration and error handling
patterns for the multi-agent deep research system.
"""

import logging
import sys
from typing import Any


# Configure logger for the multi-agent system
def setup_multi_agent_logging(log_level: str = "INFO") -> None:
    """
    Set up logging configuration for the multi-agent system.

    Args:
        log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


class MultiAgentError(Exception):
    """Base exception for multi-agent system errors."""

    def __init__(
        self,
        message: str,
        agent_type: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.agent_type = agent_type
        self.task_id = task_id
        super().__init__(message)


class AgentTaskError(MultiAgentError):
    """Exception raised when an agent task fails."""

    pass


class WorkflowCoordinationError(MultiAgentError):
    """Exception raised when workflow coordination fails."""

    pass


class SourceTrackingError(MultiAgentError):
    """Exception raised when source tracking fails."""

    pass


def log_agent_task_start(
    agent_type: str, task_id: str, task_details: dict[str, Any]
) -> None:
    """
    Log the start of an agent task.

    Args:
        agent_type (str): Type of agent executing the task.
        task_id (str): Unique task identifier.
        task_details (Dict[str, Any]): Task details and parameters.
    """
    logger = logging.getLogger(f"agents.deep_research.{agent_type}")
    logger.info(f"Starting task {task_id}: {task_details.get('task_type', 'unknown')}")


def log_agent_task_completion(
    agent_type: str, task_id: str, success: bool, error_message: str | None = None
) -> None:
    """
    Log the completion of an agent task.

    Args:
        agent_type (str): Type of agent that executed the task.
        task_id (str): Unique task identifier.
        success (bool): Whether the task completed successfully.
        error_message (Optional[str]): Error message if task failed.
    """
    logger = logging.getLogger(f"agents.deep_research.{agent_type}")
    if success:
        logger.info(f"Task {task_id} completed successfully")
    else:
        logger.error(f"Task {task_id} failed: {error_message}")


def log_workflow_event(
    workflow_id: str, event_type: str, details: dict[str, Any]
) -> None:
    """
    Log workflow coordination events.

    Args:
        workflow_id (str): Unique workflow identifier.
        event_type (str): Type of workflow event.
        details (Dict[str, Any]): Event details and context.
    """
    logger = logging.getLogger("agents.deep_research.workflow")
    logger.info(f"Workflow {workflow_id} - {event_type}: {details}")


# Module exports
__all__ = [
    "setup_multi_agent_logging",
    "MultiAgentError",
    "AgentTaskError",
    "WorkflowCoordinationError",
    "SourceTrackingError",
    "log_agent_task_start",
    "log_agent_task_completion",
    "log_workflow_event",
]
