"""
Research Workflow Coordinator implementation.

This module implements the concrete workflow coordination logic for the
multi-agent deep research system.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from ..shared import (
    AgentResult,
    AgentTask,
    MessageBus,
    ResearchWorkflow,
    ResearchWorkflowCoordinator,
    WorkflowStorage,
)

logger = logging.getLogger(__name__)


class ConcreteResearchWorkflowCoordinator(ResearchWorkflowCoordinator):
    """Concrete implementation of the research workflow coordinator."""

    def __init__(self, storage: WorkflowStorage, bus: MessageBus) -> None:
        super().__init__(storage, bus)
        self._active_workflows: dict[str, ResearchWorkflow] = {}

    async def start_research_workflow(self, query: str) -> str:
        """Initiate a new research workflow."""
        workflow_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Create initial workflow
        workflow = ResearchWorkflow(
            workflow_id=workflow_id,
            original_query=query,
            current_phase="decomposition",
            source_tracking_enabled=True,
            source_registry_id=workflow_id,  # Use workflow_id as registry identifier
            created_at=timestamp,
            updated_at=timestamp,
        )

        # Store workflow
        self._active_workflows[workflow_id] = workflow
        self._storage.create_workflow(workflow)

        # Create initial query decomposition task
        initial_task = AgentTask(
            task_id=str(uuid.uuid4()),
            agent_type="query_decomposition",
            task_type="decompose_query",
            input_data={"query": query, "workflow_id": workflow_id},
            priority=1,
            created_at=timestamp,
        )

        # Add task to workflow and assign it
        workflow.active_tasks.append(initial_task)
        self._storage.update_workflow(workflow)
        await self.assign_task_to_agent(initial_task)

        logger.info(f"Started research workflow {workflow_id} for query: {query}")
        return workflow_id

    async def assign_task_to_agent(self, task: AgentTask) -> str:
        """Assign a task to the appropriate specialized agent."""
        # Update task status
        task.status = "assigned"
        task.assigned_at = datetime.now().isoformat()

        # Note: Task updates are managed through workflow updates

        # Publish task assignment message
        message = {
            "type": "task_assignment",
            "task_id": task.task_id,
            "agent_type": task.agent_type,
            "task_data": task.model_dump(),
        }
        await self._bus.publish(message)

        logger.info(f"Assigned task {task.task_id} to {task.agent_type} agent")
        return task.task_id

    async def process_agent_result(self, result: AgentResult) -> list[AgentTask]:
        """Process results from an agent and generate follow-up tasks."""
        logger.info(
            f"Processing result from {result.agent_type} agent for task {result.task_id}"
        )

        # Validate the result data
        validation_issues = self._validate_agent_result_data(result)
        if validation_issues:
            logger.warning(
                f"Validation issues found for result {result.task_id}: {validation_issues}"
            )

        # Update workflow with completed task
        workflow = await self._get_workflow_for_task(result.task_id)
        if workflow:
            # Remove from active tasks
            workflow.active_tasks = [
                t for t in workflow.active_tasks if t.task_id != result.task_id
            ]

            # Add to completed tasks
            workflow.completed_tasks.append(result)
            workflow.updated_at = datetime.now().isoformat()

            # Update workflow phase based on completed work
            workflow.current_phase = self._determine_next_phase(workflow)

            # Validate workflow state
            state_issues = self._validate_workflow_state(workflow)
            if state_issues:
                logger.warning(
                    f"Workflow state issues for {workflow.workflow_id}: {state_issues}"
                )

            self._storage.update_workflow(workflow)

        # Generate follow-up tasks based on result
        follow_up_tasks = await self._generate_follow_up_tasks(result, workflow)

        # Assign follow-up tasks
        for task in follow_up_tasks:
            if workflow:
                workflow.active_tasks.append(task)
                self._storage.update_workflow(workflow)
            await self.assign_task_to_agent(task)

        logger.info(
            f"Processed result for task {result.task_id}, "
            f"generated {len(follow_up_tasks)} follow-up tasks"
        )
        return follow_up_tasks

    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any]:
        """Get current status of a research workflow."""
        workflow = self._active_workflows.get(workflow_id)
        if not workflow:
            workflow = self._storage.get_workflow(workflow_id)

        if not workflow:
            return {"error": f"Workflow {workflow_id} not found"}

        return {
            "workflow_id": workflow_id,
            "original_query": workflow.original_query,
            "current_phase": workflow.current_phase,
            "active_tasks": len(workflow.active_tasks),
            "completed_tasks": len(workflow.completed_tasks),
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
            "workflow_state": workflow.workflow_state,
        }

    async def _get_workflow_for_task(self, task_id: str) -> ResearchWorkflow | None:
        """Get the workflow associated with a task."""
        # Find workflow containing this task
        for workflow in self._active_workflows.values():
            for task in workflow.active_tasks:
                if task.task_id == task_id:
                    return workflow

        # If not found in active workflows, search all workflows in storage
        for _workflow_id, workflow in self._storage._workflows.items():
            for task in workflow.active_tasks:
                if task.task_id == task_id:
                    return workflow

        return None

    def _determine_next_phase(self, workflow: ResearchWorkflow) -> str:
        """Determine the next phase based on completed work."""
        completed_types = {result.agent_type for result in workflow.completed_tasks}

        if "query_decomposition" not in completed_types:
            return "decomposition"
        if not any(t in completed_types for t in ["web_research", "social_research"]):
            return "research"
        if "analysis" not in completed_types:
            return "analysis"
        if "synthesis" not in completed_types:
            return "synthesis"
        return "completed"

    async def _generate_follow_up_tasks(
        self, result: AgentResult, workflow: ResearchWorkflow | None
    ) -> list[AgentTask]:
        """Generate follow-up tasks based on agent results."""
        follow_up_tasks = []
        timestamp = datetime.now().isoformat()

        if result.agent_type == "query_decomposition":
            # Generate research tasks from decomposed queries
            if result.success and "sub_queries" in result.result_data:
                for _i, sub_query in enumerate(result.result_data["sub_queries"]):
                    # Create web research task
                    web_task = AgentTask(
                        task_id=str(uuid.uuid4()),
                        agent_type="web_research",
                        task_type="search_web",
                        input_data={
                            "query": sub_query,
                            "workflow_id": workflow.workflow_id if workflow else "",
                        },
                        priority=3,
                        dependencies=[result.task_id],
                        created_at=timestamp,
                    )
                    follow_up_tasks.append(web_task)

                    # Create social research task
                    social_task = AgentTask(
                        task_id=str(uuid.uuid4()),
                        agent_type="social_research",
                        task_type="search_social",
                        input_data={
                            "query": sub_query,
                            "workflow_id": workflow.workflow_id if workflow else "",
                        },
                        priority=3,
                        dependencies=[result.task_id],
                        created_at=timestamp,
                    )
                    follow_up_tasks.append(social_task)

        elif result.agent_type in ["web_research", "social_research"]:
            # Check if we have enough research results to start analysis
            if workflow:
                research_results = [
                    r
                    for r in workflow.completed_tasks
                    if r.agent_type in ["web_research", "social_research"]
                ]

                # Check if analysis task already exists (completed or active)
                analysis_exists = any(
                    task.agent_type == "analysis"
                    for task in (workflow.completed_tasks + workflow.active_tasks)
                )

                # If we have multiple research results and no analysis task yet, start analysis
                if len(research_results) >= 2 and not analysis_exists:
                    logger.info(
                        f"Creating analysis task with {len(research_results)} research results"
                    )

                    # Prepare comprehensive input data for analysis agent
                    analysis_input = {
                        "query": workflow.original_query,
                        "research_results": [
                            {
                                "agent_type": r.agent_type,
                                "task_id": r.task_id,
                                "result_data": r.result_data,
                                "sources_used": r.sources_used,
                                "success": r.success,
                            }
                            for r in research_results
                        ],
                        "workflow_id": workflow.workflow_id,
                    }

                    analysis_task = AgentTask(
                        task_id=str(uuid.uuid4()),
                        agent_type="analysis",
                        task_type="analyze_sources",
                        input_data=analysis_input,
                        priority=4,
                        dependencies=[r.task_id for r in research_results],
                        created_at=timestamp,
                    )
                    follow_up_tasks.append(analysis_task)

        elif result.agent_type == "analysis" and workflow:
            # Check if synthesis task already exists (completed or active)
            synthesis_exists = any(
                task.agent_type == "synthesis"
                for task in (workflow.completed_tasks + workflow.active_tasks)
            )

            if not synthesis_exists:
                logger.info("Creating synthesis task after analysis completion")

                # Prepare comprehensive input data for synthesis agent
                synthesis_input = {
                    "query": workflow.original_query,
                    "analysis_result": result.result_data,
                    "all_research_data": [
                        {
                            "agent_type": r.agent_type,
                            "task_id": r.task_id,
                            "result_data": r.result_data,
                            "sources_used": r.sources_used,
                            "success": r.success,
                        }
                        for r in workflow.completed_tasks
                    ],
                    "workflow_id": workflow.workflow_id,
                }

                # Start synthesis after analysis is complete
                synthesis_task = AgentTask(
                    task_id=str(uuid.uuid4()),
                    agent_type="synthesis",
                    task_type="synthesize_findings",
                    input_data=synthesis_input,
                    priority=5,
                    dependencies=[result.task_id],
                    created_at=timestamp,
                )
                follow_up_tasks.append(synthesis_task)

        return follow_up_tasks

    async def complete_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Mark a workflow as complete and return final results."""
        workflow = self._active_workflows.get(workflow_id)
        if not workflow:
            workflow = self._storage.get_workflow(workflow_id)

        if not workflow:
            return {"error": f"Workflow {workflow_id} not found"}

        # Find synthesis result
        synthesis_results = [
            r for r in workflow.completed_tasks if r.agent_type == "synthesis"
        ]

        if not synthesis_results:
            return {"error": "Workflow not complete - no synthesis results found"}

        # Mark workflow as complete
        workflow.current_phase = "completed"
        workflow.updated_at = datetime.now().isoformat()
        self._storage.update_workflow(workflow)

        # Remove from active workflows
        if workflow_id in self._active_workflows:
            del self._active_workflows[workflow_id]

        final_result = synthesis_results[-1].result_data

        logger.info(f"Completed workflow {workflow_id}")
        return {
            "workflow_id": workflow_id,
            "status": "completed",
            "final_result": final_result,
            "total_tasks": len(workflow.completed_tasks),
        }

    async def handle_failed_task(self, task_id: str, error_message: str) -> None:
        """Handle a failed task execution with appropriate recovery mechanisms.

        Args:
            task_id: The ID of the failed task.
            error_message: The error message from the failed execution.
        """
        logger.error(f"Task {task_id} failed: {error_message}")

        # Find the workflow containing this task
        workflow = await self._get_workflow_for_task(task_id)
        if not workflow:
            logger.error(f"No workflow found for failed task {task_id}")
            return

        # Find and remove the failed task from active tasks
        failed_task = None
        for i, task in enumerate(workflow.active_tasks):
            if task.task_id == task_id:
                failed_task = workflow.active_tasks.pop(i)
                break

        if not failed_task:
            logger.error(f"Failed task {task_id} not found in active tasks")
            return

        # Create a failed result entry
        failed_result = AgentResult(
            task_id=task_id,
            agent_type=failed_task.agent_type,
            result_data={"error": error_message, "failed": True},
            success=False,
            error_message=error_message,
            completion_time=datetime.now().isoformat(),
        )

        # Add to completed tasks for tracking
        workflow.completed_tasks.append(failed_result)
        workflow.updated_at = datetime.now().isoformat()

        # Update workflow state
        self._storage.update_workflow(workflow)

        # For critical failures, we might want to retry or create alternative tasks
        # For now, just log and continue with workflow
        logger.info(
            f"Marked task {task_id} as failed in workflow {workflow.workflow_id}"
        )

    def _validate_workflow_state(self, workflow: ResearchWorkflow) -> list[str]:
        """Validate workflow state and return any issues found.

        Args:
            workflow: The workflow to validate.

        Returns:
            List of validation issues found.
        """
        issues = []

        # Check for orphaned tasks (active tasks with no dependencies met)
        for task in workflow.active_tasks:
            if task.dependencies:
                completed_task_ids = {r.task_id for r in workflow.completed_tasks}
                unmet_deps = set(task.dependencies) - completed_task_ids
                if unmet_deps:
                    issues.append(
                        f"Task {task.task_id} has unmet dependencies: {unmet_deps}"
                    )

        # Check phase consistency
        expected_phase = self._determine_next_phase(workflow)
        if workflow.current_phase != expected_phase:
            issues.append(
                f"Workflow phase mismatch: current={workflow.current_phase}, "
                f"expected={expected_phase}"
            )

        return issues

    def _validate_agent_result_data(self, result: AgentResult) -> list[str]:
        """Validate agent result data format and content.

        Args:
            result: The agent result to validate.

        Returns:
            List of validation issues found.
        """
        issues = []

        # Basic validation
        if not result.success and not result.error_message:
            issues.append(f"Failed result {result.task_id} missing error message")

        if not result.result_data:
            issues.append(f"Result {result.task_id} has empty result_data")

        # Agent-specific validation
        if result.agent_type == "query_decomposition":
            if "sub_queries" not in result.result_data:
                issues.append(
                    f"Query decomposition result {result.task_id} missing sub_queries"
                )
            elif not isinstance(result.result_data["sub_queries"], list):
                issues.append(
                    f"Query decomposition result {result.task_id} sub_queries not a list"
                )

        elif result.agent_type in ["web_research", "social_research"]:
            # Research results should have some content
            if result.success and not result.sources_used:
                issues.append(f"Research result {result.task_id} has no sources_used")

        elif result.agent_type == "analysis":
            # Analysis should provide structured assessment
            if result.success and "analysis" not in result.result_data:
                issues.append(f"Analysis result {result.task_id} missing analysis data")

        elif (
            result.agent_type == "synthesis"
            and result.success
            and "report" not in result.result_data
        ):
            # Synthesis should provide final report
            issues.append(f"Synthesis result {result.task_id} missing report data")

        return issues
