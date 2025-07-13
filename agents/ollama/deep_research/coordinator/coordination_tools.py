"""
Coordination tools for the Research Coordinator Agent.

This module provides simple, serializable tools for workflow coordination
in the multi-agent research system.
"""

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Import specialized agents for task execution
from ..analysis.agent import analysis_tool
from ..query_decomposition.agent import query_decomposition_tool
from ..shared import (
    AgentResult,
    AgentSourceTracker,
    MessageBus,
    SharedSourceRegistry,
    WorkflowStorage,
)
from ..social_research.agent import social_research_tool
from ..synthesis.agent import synthesis_tool
from ..web_research.agent import web_research_tool
from .workflow_coordinator import ConcreteResearchWorkflowCoordinator

logger = logging.getLogger(__name__)


# Pydantic response models for strongly typed, documented API responses
class WorkflowInitiationResponse(BaseModel):
    """Response from initiating a research workflow."""

    success: bool = Field(..., description="Whether the workflow was successfully initiated")
    workflow_id: str = Field(..., description="Unique identifier for the created workflow")
    message: str = Field(..., description="Human-readable status message")
    initial_phase: str = Field(..., description="The first phase of the workflow")


class WorkflowStatusResponse(BaseModel):
    """Response containing workflow status information."""

    success: bool = Field(..., description="Whether the status was successfully retrieved")
    workflow_id: str = Field(..., description="The workflow identifier")
    current_phase: str = Field(..., description="Current workflow phase")
    completed_tasks: int = Field(..., description="Number of completed tasks")
    pending_tasks: int = Field(..., description="Number of pending tasks")
    status: str = Field(..., description="Overall workflow status")


class AgentResultProcessingResponse(BaseModel):
    """Response from processing an agent's task result."""

    success: bool = Field(..., description="Whether the result was successfully processed")
    processed_task_id: str = Field(..., description="ID of the task that was processed")
    follow_up_tasks_created: int = Field(..., description="Number of follow-up tasks created")
    follow_up_task_ids: list[str] = Field(..., description="IDs of created follow-up tasks")
    message: str = Field(..., description="Human-readable processing summary")


class WorkflowCompletionResponse(BaseModel):
    """Response from completing a workflow."""

    success: bool = Field(..., description="Whether the workflow was successfully completed")
    workflow_id: str = Field(..., description="The completed workflow identifier")
    final_report: str = Field(..., description="Final research report or summary")
    total_sources: int = Field(..., description="Total number of sources processed")
    completion_time: str = Field(..., description="Workflow completion timestamp")


class TaskExecutionResponse(BaseModel):
    """Response from executing an agent task."""

    success: bool = Field(..., description="Whether the task was successfully executed")
    task_id: str = Field(..., description="The executed task identifier")
    agent_type: str = Field(..., description="Type of agent that executed the task")
    result: str = Field(..., description="JSON string containing the agent's results")
    message: str = Field(..., description="Human-readable execution summary")


class ErrorResponse(BaseModel):
    """Standard error response format."""

    success: bool = Field(False, description="Always false for error responses")
    error: str = Field(..., description="Error message describing what went wrong")
    error_code: str = Field(..., description="Machine-readable error code")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional error context")


class CoordinationTools:
    """Simple coordination tools for research workflow management."""

    def __init__(self, agent_id: str) -> None:
        """Initialize coordination tools.

        Args:
            agent_id: Unique identifier for this agent instance.
        """
        self.agent_id = agent_id

        # Initialize source tracking for this agent
        source_registry = SharedSourceRegistry()
        self.source_tracker = AgentSourceTracker(agent_id, source_registry)

        # Initialize workflow infrastructure
        self.storage = WorkflowStorage()
        self.bus = MessageBus()
        self.coordinator = ConcreteResearchWorkflowCoordinator(self.storage, self.bus)

    async def initiate_research_workflow(self, query: str) -> WorkflowInitiationResponse:
        """Initiate a new multi-agent research workflow.

        Args:
            query: The research query to investigate.

        Returns:
            WorkflowInitiationResponse with workflow ID and status information.

        Raises:
            Exception: If workflow initiation fails.
        """
        try:
            workflow_id = await self.coordinator.start_research_workflow(query)

            logger.info(f"Initiated workflow {workflow_id} for query: {query}")
            return WorkflowInitiationResponse(
                success=True,
                workflow_id=workflow_id,
                message=f"Started research workflow for: {query}",
                initial_phase="decomposition",
            )

        except Exception as e:
            logger.error(f"Failed to initiate workflow: {e}")
            raise

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatusResponse:
        """Get the current status of a research workflow.

        Args:
            workflow_id: The ID of the workflow to check.

        Returns:
            WorkflowStatusResponse containing workflow status information.

        Raises:
            Exception: If status retrieval fails.
        """
        try:
            status = await self.coordinator.get_workflow_status(workflow_id)

            logger.info(f"Retrieved status for workflow {workflow_id}")
            return WorkflowStatusResponse(
                success=True,
                workflow_id=workflow_id,
                current_phase=status.get("current_phase", "unknown"),
                completed_tasks=status.get("completed_tasks", 0),
                pending_tasks=status.get("pending_tasks", 0),
                status=status.get("status", "unknown"),
            )

        except Exception as e:
            logger.error(f"Failed to get workflow status: {e}")
            raise

    async def process_agent_result(
        self, task_id: str, agent_type: str, result_data: str, success: bool
    ) -> AgentResultProcessingResponse:
        """Process results from a specialized agent.

        Args:
            task_id: The ID of the completed task.
            agent_type: The type of agent that completed the task.
            result_data: JSON string containing the agent's results.
            success: Whether the task completed successfully.

        Returns:
            AgentResultProcessingResponse containing follow-up task information.

        Raises:
            Exception: If result processing fails.
        """
        try:
            # Parse result data
            parsed_data = (
                json.loads(result_data) if isinstance(result_data, str) else result_data
            )

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

            logger.info(
                f"Processed result for task {task_id}, created {len(follow_up_tasks)} follow-up tasks"
            )
            return AgentResultProcessingResponse(
                success=True,
                processed_task_id=task_id,
                follow_up_tasks_created=len(follow_up_tasks),
                follow_up_task_ids=[task.task_id for task in follow_up_tasks],
                message=f"Processed result from {agent_type} agent",
            )

        except Exception as e:
            logger.error(f"Failed to process agent result: {e}")
            raise

    async def complete_workflow(self, workflow_id: str) -> WorkflowCompletionResponse:
        """Mark a workflow as complete and get final results.

        Args:
            workflow_id: The ID of the workflow to complete.

        Returns:
            WorkflowCompletionResponse containing final workflow results.

        Raises:
            Exception: If workflow completion fails.
        """
        try:
            result = await self.coordinator.complete_workflow(workflow_id)

            logger.info(f"Completed workflow {workflow_id}")
            return WorkflowCompletionResponse(
                success=True,
                workflow_id=workflow_id,
                final_report=result.get("final_report", ""),
                total_sources=result.get("total_sources", 0),
                completion_time=self._get_current_timestamp(),
            )

        except Exception as e:
            logger.error(f"Failed to complete workflow: {e}")
            raise

    async def execute_agent_task(
        self, task_id: str, agent_type: str, query: str
    ) -> TaskExecutionResponse:
        """Execute a task using the appropriate specialized agent.

        Args:
            task_id: The ID of the task to execute.
            agent_type: The type of agent to use (web_research, social_research, etc.).
            query: The research query for the agent to process.

        Returns:
            TaskExecutionResponse containing task execution results.

        Raises:
            ValueError: If query is empty or agent_type is not supported.
            Exception: If task execution fails.
        """
        # Validate input
        if not query.strip():
            raise ValueError("Empty query provided")

        # Log task execution details
        logger.info(f"Executing {agent_type} task {task_id} with query: '{query}'")

        # Execute task based on agent type
        if agent_type == "query_decomposition":
            result = await query_decomposition_tool(query)
        elif agent_type == "web_research":
            result = await web_research_tool(query)
        elif agent_type == "social_research":
            result = await social_research_tool(query)
        elif agent_type == "analysis":
            result = await analysis_tool(query)
        elif agent_type == "synthesis":
            result = await synthesis_tool(query)
        else:
            raise ValueError(f"Agent type '{agent_type}' not yet implemented")

        logger.info(f"Executed task {task_id} using {agent_type} agent")
        return TaskExecutionResponse(
            success=True,
            task_id=task_id,
            agent_type=agent_type,
            result=json.dumps(result) if not isinstance(result, str) else result,
            message=f"Successfully executed {agent_type} task",
        )

    def get_coordination_guidelines(self) -> str:
        """Get guidelines for coordinating multi-agent research workflows.

        Returns:
            String containing workflow coordination guidelines.
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
        """Get current timestamp in ISO format.

        Returns:
            ISO formatted timestamp string.
        """
        return datetime.now().isoformat()
