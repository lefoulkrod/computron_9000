"""Agent task tools for the enhanced task system.

This module provides the single task-related tool that agents use to
retrieve their assigned task data from the centralized storage.
"""

import json
import logging
from typing import Any

from .task_data_storage import retrieve_task_data

logger = logging.getLogger(__name__)


def get_task_data(task_id: str) -> str:
    """Retrieve task data for an assigned task.

    This is the only task-related tool available to agents. Agents must call
    this tool at the beginning of their execution to retrieve their task
    configuration and parameters.

    Args:
        task_id: Unique identifier for the task assigned to this agent

    Returns:
        JSON string containing the task data with all configuration parameters

    Raises:
        KeyError: If task_id is not found
        ValueError: If task_id is empty or invalid
    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Convert to JSON for agent consumption
        task_data_dict = task_data.model_dump()
        result_json = json.dumps(task_data_dict, indent=2)

        logger.info(
            f"Retrieved task data for task {task_id} "
            f"(agent: {task_data.agent_type})"
        )

        return result_json

    except KeyError as e:
        error_msg = f"Task not found: {e}"
        logger.error(error_msg)
        raise KeyError(error_msg) from e

    except ValueError as e:
        error_msg = f"Invalid task ID: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

    except Exception as e:
        error_msg = f"Failed to retrieve task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


# Tool metadata for JSON schema generation
GET_TASK_DATA_TOOL_SCHEMA = {
    "name": "get_task_data",
    "description": (
        "Retrieve task data for the assigned task. "
        "MANDATORY: This tool must be called at the beginning of agent execution "
        "to get task configuration, parameters, and context. "
        "The returned data contains all necessary information for completing the task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Unique identifier for the task assigned to this agent",
            }
        },
        "required": ["task_id"],
    },
    "returns": {
        "type": "string",
        "description": (
            "JSON string containing complete task data including: "
            "task_id, workflow_id, agent_type, created_at, and agent-specific "
            "configuration parameters (search queries, options, context, etc.)"
        ),
    },
}


def get_task_data_tool_schema() -> dict[str, Any]:
    """Get the JSON schema for the get_task_data tool.

    Returns:
        JSON schema dictionary for tool registration
    """
    return GET_TASK_DATA_TOOL_SCHEMA.copy()


# For backward compatibility and explicit imports
__all__ = [
    "get_task_data",
    "get_task_data_tool_schema",
    "GET_TASK_DATA_TOOL_SCHEMA",
]
