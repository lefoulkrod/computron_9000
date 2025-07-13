"""
Utility functions for managing source trackers in the multi-agent workflow system.

This module provides convenience functions for creating and managing agent-specific
source trackers that are linked to the workflow's shared source registry.
"""

import logging
from datetime import datetime
from typing import Any

from .source_tracking import AgentSourceTracker, SharedSourceRegistry
from .storage import get_storage

logger = logging.getLogger(__name__)


def create_agent_source_tracker(
    agent_id: str, workflow_id: str
) -> AgentSourceTracker:
    """
    Create an agent-specific source tracker linked to the workflow's shared registry.

    Args:
        agent_id (str): Unique identifier for the agent.
        workflow_id (str): Workflow ID to link the tracker to.

    Returns:
        AgentSourceTracker: Configured source tracker for the agent.

    Raises:
        ValueError: If workflow not found or source registry not available.
    """
    storage = get_storage()
    
    # Get the shared source registry for the workflow
    shared_registry = storage.get_source_registry(workflow_id)
    if not shared_registry:
        raise ValueError(f"No source registry found for workflow {workflow_id}")

    # Create agent-specific tracker
    tracker = AgentSourceTracker(agent_id, shared_registry)
    
    logger.info(f"Created source tracker for agent {agent_id} in workflow {workflow_id}")
    return tracker


def get_workflow_source_summary(workflow_id: str) -> dict[str, Any]:
    """
    Get a comprehensive summary of source tracking for a workflow.

    Args:
        workflow_id (str): The workflow ID.

    Returns:
        dict: Summary of sources, accesses, and agent activity.

    Raises:
        ValueError: If workflow not found.
    """
    storage = get_storage()
    
    workflow = storage.get_workflow(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow {workflow_id} not found")

    shared_registry = storage.get_source_registry(workflow_id)
    if not shared_registry:
        return {
            "workflow_id": workflow_id,
            "source_tracking_enabled": workflow.source_tracking_enabled,
            "total_sources": 0,
            "total_accesses": 0,
            "active_agents": [],
            "source_breakdown": {},
            "agent_activity": {},
        }

    # Get all sources and accesses
    all_sources = shared_registry.get_all_sources()
    all_accesses = shared_registry.get_all_accesses()
    
    # Group sources by type/domain
    source_breakdown = {}
    for source in all_sources:
        source_type = getattr(source, 'source_type', 'unknown')
        if source_type not in source_breakdown:
            source_breakdown[source_type] = 0
        source_breakdown[source_type] += 1

    # Get agent activity summary
    agent_activity = {}
    for access in all_accesses:
        agent_id = access.agent_id
        if agent_id not in agent_activity:
            agent_activity[agent_id] = {
                "total_accesses": 0,
                "unique_sources": set(),
                "tools_used": set(),
            }
        
        agent_activity[agent_id]["total_accesses"] += 1
        agent_activity[agent_id]["unique_sources"].add(access.url)
        agent_activity[agent_id]["tools_used"].add(access.tool_name)

    # Convert sets to counts for JSON serialization
    for agent_data in agent_activity.values():
        agent_data["unique_sources"] = len(agent_data["unique_sources"])
        agent_data["tools_used"] = list(agent_data["tools_used"])

    return {
        "workflow_id": workflow_id,
        "source_tracking_enabled": workflow.source_tracking_enabled,
        "total_sources": len(all_sources),
        "total_accesses": len(all_accesses),
        "active_agents": list(agent_activity.keys()),
        "source_breakdown": source_breakdown,
        "agent_activity": agent_activity,
    }


def export_workflow_sources(workflow_id: str, include_full_content: bool = False) -> dict[str, Any]:
    """
    Export all sources and tracking data for a workflow.

    Args:
        workflow_id (str): The workflow ID.
        include_full_content (bool): Whether to include full source content.

    Returns:
        dict: Complete source tracking export.

    Raises:
        ValueError: If workflow not found.
    """
    storage = get_storage()
    
    shared_registry = storage.get_source_registry(workflow_id)
    if not shared_registry:
        raise ValueError(f"No source registry found for workflow {workflow_id}")

    export_data = shared_registry.to_dict()
    
    if not include_full_content:
        # Remove content field from sources to reduce size
        for source_data in export_data.get("sources", {}).values():
            source_data.pop("content", None)

    export_data["export_metadata"] = {
        "workflow_id": workflow_id,
        "export_timestamp": datetime.now().isoformat(),
        "include_full_content": include_full_content,
    }

    return export_data


def import_workflow_sources(workflow_id: str, source_data: dict[str, Any]) -> None:
    """
    Import source tracking data into a workflow.

    Args:
        workflow_id (str): The workflow ID to import into.
        source_data (dict): Source tracking data to import.

    Raises:
        ValueError: If workflow not found or data format invalid.
    """
    storage = get_storage()
    
    workflow = storage.get_workflow(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow {workflow_id} not found")

    # Restore the shared registry from imported data
    try:
        imported_registry = SharedSourceRegistry.from_dict(source_data)
        storage._source_registries[workflow_id] = imported_registry
        logger.info(f"Imported source tracking data for workflow {workflow_id}")
    except Exception as e:
        raise ValueError(f"Invalid source data format: {e}")


def clear_workflow_sources(workflow_id: str) -> None:
    """
    Clear all source tracking data for a workflow.

    Args:
        workflow_id (str): The workflow ID.

    Raises:
        ValueError: If workflow not found.
    """
    storage = get_storage()
    
    shared_registry = storage.get_source_registry(workflow_id)
    if not shared_registry:
        raise ValueError(f"No source registry found for workflow {workflow_id}")

    shared_registry.clear()
    logger.info(f"Cleared source tracking data for workflow {workflow_id}")


# Module exports
__all__ = [
    "create_agent_source_tracker",
    "get_workflow_source_summary",
    "export_workflow_sources",
    "import_workflow_sources",
    "clear_workflow_sources",
]
