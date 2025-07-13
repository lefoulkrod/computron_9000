"""
Coordination tools for the Research Coordinator Agent.

This module provides tools for workflow initiation, task delegation,
and result processing in the multi-agent research system.
"""

import json
import logging
from typing import Any

from ..shared import (
    AgentResult,
    AgentSourceTracker,
    MessageBus,
    SharedSourceRegistry,
    WorkflowStorage,
)
from .workflow_coordinator import ConcreteResearchWorkflowCoordinator

logger = logging.getLogger(__name__)


class CoordinationTools:
    """Tools for research workflow coordination."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        
        # Initialize source tracking for this agent
        source_registry = SharedSourceRegistry()
        self.source_tracker = AgentSourceTracker(agent_id, source_registry)
        
        # Initialize workflow infrastructure
        self.storage = WorkflowStorage()
        self.bus = MessageBus()
        self.coordinator = ConcreteResearchWorkflowCoordinator(self.storage, self.bus)

    async def initiate_research_workflow(self, query: str) -> str:
        """
        Initiate a new multi-agent research workflow.
        
        Args:
            query: The research query to investigate
            
        Returns:
            JSON string with workflow ID and initial status
        """
        try:
            workflow_id = await self.coordinator.start_research_workflow(query)
            
            result = {
                "success": True,
                "workflow_id": workflow_id,
                "message": f"Started research workflow for: {query}",
                "initial_phase": "decomposition",
            }
            
            logger.info(f"Initiated workflow {workflow_id} for query: {query}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to initiate research workflow",
            }
            logger.error(f"Failed to initiate workflow: {e}")
            return json.dumps(error_result, indent=2)

    async def get_workflow_status(self, workflow_id: str) -> str:
        """
        Get the current status of a research workflow.
        
        Args:
            workflow_id: The ID of the workflow to check
            
        Returns:
            JSON string with workflow status information
        """
        try:
            status = await self.coordinator.get_workflow_status(workflow_id)
            
            logger.info(f"Retrieved status for workflow {workflow_id}")
            return json.dumps(status, indent=2)
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "workflow_id": workflow_id,
            }
            logger.error(f"Failed to get workflow status: {e}")
            return json.dumps(error_result, indent=2)

    async def process_agent_result(
        self, task_id: str, agent_type: str, result_data: str, success: bool = True
    ) -> str:
        """
        Process results from a specialized agent and generate follow-up tasks.
        
        Args:
            task_id: The ID of the completed task
            agent_type: The type of agent that completed the task
            result_data: JSON string containing the agent's results
            success: Whether the task completed successfully
            
        Returns:
            JSON string with follow-up task information
        """
        try:
            # Parse result data
            parsed_data = json.loads(result_data) if isinstance(result_data, str) else result_data
            
            # Create agent result object
            agent_result = AgentResult(
                task_id=task_id,
                agent_type=agent_type,
                result_data=parsed_data,
                success=success,
                completion_time=self._get_current_timestamp(),
            )
            
            # Process the result and get follow-up tasks
            follow_up_tasks = await self.coordinator.process_agent_result(agent_result)
            
            result = {
                "success": True,
                "processed_task_id": task_id,
                "follow_up_tasks_created": len(follow_up_tasks),
                "follow_up_task_ids": [task.task_id for task in follow_up_tasks],
                "message": f"Processed result from {agent_type} agent",
            }
            
            logger.info(
                f"Processed result for task {task_id}, created {len(follow_up_tasks)} follow-up tasks"
            )
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "task_id": task_id,
                "agent_type": agent_type,
            }
            logger.error(f"Failed to process agent result: {e}")
            return json.dumps(error_result, indent=2)

    async def complete_workflow(self, workflow_id: str) -> str:
        """
        Mark a workflow as complete and get final results.
        
        Args:
            workflow_id: The ID of the workflow to complete
            
        Returns:
            JSON string with final workflow results
        """
        try:
            result = await self.coordinator.complete_workflow(workflow_id)
            
            logger.info(f"Completed workflow {workflow_id}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "workflow_id": workflow_id,
            }
            logger.error(f"Failed to complete workflow: {e}")
            return json.dumps(error_result, indent=2)

    def get_coordination_guidelines(self) -> str:
        """
        Get guidelines for coordinating multi-agent research workflows.
        
        Returns:
            Guidelines for effective workflow coordination
        """
        guidelines = """
        # Research Coordination Guidelines

        ## Workflow Phases
        1. **Decomposition**: Break down complex queries into manageable sub-queries
        2. **Research**: Parallel execution of web and social research tasks
        3. **Analysis**: Cross-reference verification and source credibility assessment
        4. **Synthesis**: Combine findings into comprehensive report with citations

        ## Best Practices
        - **Task Delegation**: Assign tasks to specialized agents based on their capabilities
        - **Parallel Processing**: Execute independent research tasks concurrently
        - **Progress Tracking**: Monitor workflow status and agent completion
        - **Error Handling**: Gracefully handle agent failures and retry failed tasks
        - **Resource Management**: Track sources across agents to avoid duplication

        ## Coordination Strategies
        - Start with query decomposition to identify research scope
        - Launch web and social research tasks in parallel after decomposition
        - Begin analysis only after sufficient research data is collected
        - Initiate synthesis when analysis and all research tasks are complete
        - Maintain workflow state for progress tracking and recovery

        ## Quality Assurance
        - Verify task completion before proceeding to next phase
        - Validate agent results for completeness and accuracy
        - Ensure proper source tracking and citation management
        - Monitor for contradictions or inconsistencies across sources
        """
        
        return guidelines.strip()

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()
