"""Agent task tools for the enhanced task system.

This module provides strongly typed task-related tools that agents use to
retrieve their assigned task data from the centralized storage with proper
type safety for each agent type.
"""

import json
import logging

from .task_data_storage import retrieve_task_data
from .task_data_types import (
    AnalysisTaskData,
    QueryDecompositionTaskData,
    SocialResearchTaskData,
    SynthesisTaskData,
    WebResearchTaskData,
)

logger = logging.getLogger(__name__)


def get_task_data(task_id: str) -> str:
    """Retrieve task data for any assigned task (generic version).

    This is a fallback function that can handle any task type but doesn't
    provide strong typing and returns JSON. Prefer using the specific typed
    functions above for better type safety.

    Args:
        task_id: Unique identifier for the task assigned to this agent.

    Returns:
        JSON string containing the task data with all configuration parameters.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.

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
            f"Retrieved task data for task {task_id} (agent: {task_data.agent_type})",
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


def get_web_research_task_data(task_id: str) -> WebResearchTaskData:
    """Retrieve web research task data for an assigned task.

    This function returns a strongly typed WebResearchTaskData instance. Web research
    agents must call this tool at the beginning of their execution to retrieve their
    task configuration and parameters.

    Args:
        task_id: Unique identifier for the web research task assigned to this agent.

    Returns:
        WebResearchTaskData instance containing all web research configuration
        parameters including search_query, search_domains, max_sources, search_depth,
        content_types, and workflow context.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.
        TypeError: If the retrieved task is not a WebResearchTaskData instance.

    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Validate it's the correct type
        if not isinstance(task_data, WebResearchTaskData):
            raise TypeError(
                f"Task {task_id} is not a web research task. Got {type(task_data).__name__}",
            )

        logger.info(
            f"Retrieved web research task data for task {task_id} "
            f"(query: {task_data.search_query})",
        )

        return task_data

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"Failed to retrieve web research task data for {task_id}: {e}"
        logger.error(error_msg)
        raise type(e)(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error retrieving web research task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_social_research_task_data(task_id: str) -> SocialResearchTaskData:
    """Retrieve social research task data for an assigned task.

    This function returns a strongly typed SocialResearchTaskData instance. Social
    research agents must call this tool at the beginning of their execution to
    retrieve their task configuration and parameters.

    Args:
        task_id: Unique identifier for the social research task assigned to this agent.

    Returns:
        SocialResearchTaskData instance containing all social research configuration
        parameters including search_query, platforms, max_posts, sort_by,
        target_subreddits, and workflow context.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.
        TypeError: If the retrieved task is not a SocialResearchTaskData instance.

    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Validate it's the correct type
        if not isinstance(task_data, SocialResearchTaskData):
            raise TypeError(
                f"Task {task_id} is not a social research task. Got {type(task_data).__name__}",
            )

        logger.info(
            f"Retrieved social research task data for task {task_id} "
            f"(query: {task_data.search_query}, platforms: {task_data.platforms})",
        )

        return task_data

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"Failed to retrieve social research task data for {task_id}: {e}"
        logger.error(error_msg)
        raise type(e)(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error retrieving social research task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_analysis_task_data(task_id: str) -> AnalysisTaskData:
    """Retrieve analysis task data for an assigned task.

    This function returns a strongly typed AnalysisTaskData instance. Analysis
    agents must call this tool at the beginning of their execution to retrieve
    their task configuration and parameters.

    Args:
        task_id: Unique identifier for the analysis task assigned to this agent.

    Returns:
        AnalysisTaskData instance containing all analysis configuration parameters
        including analysis_type, analysis_questions, research_results,
        cross_verification settings, and workflow context.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.
        TypeError: If the retrieved task is not an AnalysisTaskData instance.

    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Validate it's the correct type
        if not isinstance(task_data, AnalysisTaskData):
            raise TypeError(
                f"Task {task_id} is not an analysis task. Got {type(task_data).__name__}",
            )

        logger.info(
            f"Retrieved analysis task data for task {task_id} "
            f"(type: {task_data.analysis_type}, query: {task_data.original_query})",
        )

        return task_data

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"Failed to retrieve analysis task data for {task_id}: {e}"
        logger.error(error_msg)
        raise type(e)(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error retrieving analysis task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_synthesis_task_data(task_id: str) -> SynthesisTaskData:
    """Retrieve synthesis task data for an assigned task.

    This function returns a strongly typed SynthesisTaskData instance. Synthesis
    agents must call this tool at the beginning of their execution to retrieve
    their task configuration and parameters.

    Args:
        task_id: Unique identifier for the synthesis task assigned to this agent.

    Returns:
        SynthesisTaskData instance containing all synthesis configuration parameters
        including output_format, target_audience, analysis_results, research_findings,
        and workflow context.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.
        TypeError: If the retrieved task is not a SynthesisTaskData instance.

    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Validate it's the correct type
        if not isinstance(task_data, SynthesisTaskData):
            raise TypeError(
                f"Task {task_id} is not a synthesis task. Got {type(task_data).__name__}",
            )

        logger.info(
            f"Retrieved synthesis task data for task {task_id} "
            f"(format: {task_data.output_format}, audience: {task_data.target_audience})",
        )

        return task_data

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"Failed to retrieve synthesis task data for {task_id}: {e}"
        logger.error(error_msg)
        raise type(e)(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error retrieving synthesis task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_query_decomposition_task_data(task_id: str) -> QueryDecompositionTaskData:
    """Retrieve query decomposition task data for an assigned task.

    This function returns a strongly typed QueryDecompositionTaskData instance.
    Query decomposition agents must call this tool at the beginning of their
    execution to retrieve their task configuration and parameters.

    Args:
        task_id: Unique identifier for the query decomposition task assigned to this agent.

    Returns:
        QueryDecompositionTaskData instance containing all query decomposition
        configuration parameters including original_query, max_subqueries,
        decomposition_strategy, preferred_domains, and workflow context.

    Raises:
        KeyError: If task_id is not found in storage.
        ValueError: If task_id is empty or invalid.
        TypeError: If the retrieved task is not a QueryDecompositionTaskData instance.

    """
    try:
        # Validate input
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")

        # Retrieve task data from storage
        task_data = retrieve_task_data(task_id)

        # Validate it's the correct type
        if not isinstance(task_data, QueryDecompositionTaskData):
            raise TypeError(
                f"Task {task_id} is not a query decomposition task. Got {type(task_data).__name__}",
            )

        logger.info(
            f"Retrieved query decomposition task data for task {task_id} "
            f"(query: {task_data.original_query}, strategy: {task_data.decomposition_strategy})",
        )

        return task_data

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"Failed to retrieve query decomposition task data for {task_id}: {e}"
        logger.error(error_msg)
        raise type(e)(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error retrieving query decomposition task data for {task_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


# For backward compatibility and explicit imports
__all__ = [
    # Strongly typed functions - primary interface
    "get_web_research_task_data",
    "get_social_research_task_data",
    "get_analysis_task_data",
    "get_synthesis_task_data",
    "get_query_decomposition_task_data",
    # Generic fallback (for backward compatibility)
    "get_task_data",
]
