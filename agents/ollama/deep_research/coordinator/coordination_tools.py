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

    # Research planning and coordination functionality (migrated from legacy Research Planner)
    async def create_research_coordination_plan(
        self, query: str, decomposition_result: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create a comprehensive research coordination plan based on query decomposition.

        Args:
            query (str): Original research query
            decomposition_result (Dict[str, Any]): Results from Query Decomposition Agent

        Returns:
            Dict[str, Any]: Detailed coordination plan for multi-agent execution
        """
        try:
            sub_queries = decomposition_result.get("sub_queries", [])
            dependencies = decomposition_result.get("dependencies", [])
            research_strategy = decomposition_result.get("research_strategy", {})

            # Create agent assignment plan
            agent_assignments = self._create_agent_assignments(sub_queries)

            # Create execution timeline
            execution_phases = self._create_execution_phases(
                agent_assignments, dependencies
            )

            # Estimate resource requirements
            resource_estimates = self._estimate_resource_requirements(
                sub_queries, agent_assignments
            )

            # Create quality checkpoints
            quality_checkpoints = self._create_quality_checkpoints(execution_phases)

            return {
                "original_query": query,
                "coordination_plan": {
                    "total_sub_queries": len(sub_queries),
                    "estimated_duration": resource_estimates["estimated_duration"],
                    "agent_assignments": agent_assignments,
                    "execution_phases": execution_phases,
                    "quality_checkpoints": quality_checkpoints,
                    "resource_estimates": resource_estimates,
                },
                "risk_assessment": self._assess_coordination_risks(
                    sub_queries, dependencies
                ),
                "success_criteria": self._define_success_criteria(
                    query, research_strategy
                ),
                "contingency_plans": self._create_contingency_plans(agent_assignments),
            }

        except Exception as e:
            logger.error(f"Error creating research coordination plan: {e}")
            return {
                "error": str(e),
                "coordination_plan": {},
                "risk_assessment": ["Error in planning - proceed with caution"],
                "success_criteria": [],
            }

    def _create_agent_assignments(
        self, sub_queries: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Create optimal agent assignments for sub-queries."""
        assignments: dict[str, list[dict[str, Any]]] = {
            "web_research": [],
            "social_research": [],
            "analysis": [],
            "synthesis": [],
        }

        for sub_query in sub_queries:
            query_type = sub_query.get("type", "factual")
            sources_needed = sub_query.get("sources_needed", [])

            # Determine primary agent based on query characteristics
            if any(
                source in ["reddit", "social media", "forums"]
                for source in sources_needed
            ):
                assignments["social_research"].append(
                    {
                        "sub_query": sub_query,
                        "priority": sub_query.get("priority", 5),
                        "estimated_effort": self._estimate_effort(sub_query, "social"),
                    }
                )
            elif query_type in ["analysis", "comparison", "evaluation"]:
                assignments["analysis"].append(
                    {
                        "sub_query": sub_query,
                        "priority": sub_query.get("priority", 5),
                        "estimated_effort": self._estimate_effort(
                            sub_query, "analysis"
                        ),
                    }
                )
            else:
                assignments["web_research"].append(
                    {
                        "sub_query": sub_query,
                        "priority": sub_query.get("priority", 5),
                        "estimated_effort": self._estimate_effort(sub_query, "web"),
                    }
                )

        return assignments

    def _create_execution_phases(
        self,
        agent_assignments: dict[str, list[dict[str, Any]]],
        _dependencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Create execution phases considering dependencies."""
        phases = []

        # Phase 1: Independent web and social research (parallel)
        phase1_tasks = []
        phase1_tasks.extend(agent_assignments.get("web_research", []))
        phase1_tasks.extend(agent_assignments.get("social_research", []))

        if phase1_tasks:
            phases.append(
                {
                    "phase": 1,
                    "name": "Initial Research",
                    "description": "Parallel web and social media research",
                    "tasks": phase1_tasks,
                    "dependencies": [],
                    "can_run_parallel": True,
                    "estimated_duration": max(
                        [task["estimated_effort"] for task in phase1_tasks], default=30
                    ),
                }
            )

        # Phase 2: Analysis of collected sources
        phase2_tasks = agent_assignments.get("analysis", [])
        if phase2_tasks:
            phases.append(
                {
                    "phase": 2,
                    "name": "Source Analysis",
                    "description": "Credibility assessment and cross-reference verification",
                    "tasks": phase2_tasks,
                    "dependencies": [1] if phase1_tasks else [],
                    "can_run_parallel": True,
                    "estimated_duration": max(
                        [task["estimated_effort"] for task in phase2_tasks], default=20
                    ),
                }
            )

        # Phase 3: Synthesis and final report
        phases.append(
            {
                "phase": 3,
                "name": "Synthesis",
                "description": "Combine findings and generate comprehensive report",
                "tasks": [
                    {
                        "agent": "synthesis",
                        "description": "Final synthesis and reporting",
                    }
                ],
                "dependencies": [p["phase"] for p in phases],
                "can_run_parallel": False,
                "estimated_duration": 25,
            }
        )

        return phases

    def _estimate_effort(self, sub_query: dict[str, Any], agent_type: str) -> int:
        """Estimate effort in minutes for a sub-query."""
        base_effort = {
            "web": 15,
            "social": 12,
            "analysis": 20,
            "synthesis": 25,
        }

        complexity = sub_query.get("complexity", "medium")
        complexity_multipliers = {
            "low": 0.7,
            "medium": 1.0,
            "high": 1.5,
            "very_high": 2.0,
        }

        return int(
            base_effort.get(agent_type, 15)
            * complexity_multipliers.get(complexity, 1.0)
        )

    def _estimate_resource_requirements(
        self,
        sub_queries: list[dict[str, Any]],
        agent_assignments: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Estimate overall resource requirements."""
        total_effort = 0
        agent_efforts = {}

        for agent_type, tasks in agent_assignments.items():
            agent_effort = sum(task["estimated_effort"] for task in tasks)
            agent_efforts[agent_type] = agent_effort
            total_effort += agent_effort

        # Add synthesis effort
        synthesis_effort = 25 + (len(sub_queries) * 3)  # Base + per sub-query overhead
        total_effort += synthesis_effort
        agent_efforts["synthesis"] = synthesis_effort

        return {
            "estimated_duration": total_effort,
            "agent_efforts": agent_efforts,
            "peak_parallel_load": max(agent_efforts.values()),
            "total_sub_queries": len(sub_queries),
            "complexity_assessment": self._assess_overall_complexity(sub_queries),
        }

    def _assess_overall_complexity(self, sub_queries: list[dict[str, Any]]) -> str:
        """Assess overall research complexity."""
        if not sub_queries:
            return "minimal"

        complexity_scores = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "very_high": 4,
        }

        avg_complexity = sum(
            complexity_scores.get(sq.get("complexity", "medium"), 2)
            for sq in sub_queries
        ) / len(sub_queries)

        if avg_complexity < 1.5:
            return "low"
        if avg_complexity < 2.5:
            return "medium"
        if avg_complexity < 3.5:
            return "high"
        return "very_high"

    def _create_quality_checkpoints(
        self, execution_phases: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create quality checkpoints for the research process."""
        checkpoints = []

        for phase in execution_phases:
            checkpoint = {
                "phase": phase["phase"],
                "checkpoint_name": f"Phase {phase['phase']} Quality Check",
                "criteria": [],
                "required_actions": [],
            }

            if phase["name"] == "Initial Research":
                checkpoint["criteria"] = [
                    "Minimum 3 sources per sub-query",
                    "Source credibility score > 0.4",
                    "Diverse source types (academic, news, expert)",
                ]
                checkpoint["required_actions"] = [
                    "Verify source accessibility",
                    "Check for duplicate sources",
                    "Validate source relevance",
                ]
            elif phase["name"] == "Source Analysis":
                checkpoint["criteria"] = [
                    "All sources analyzed for credibility",
                    "Cross-references identified",
                    "Contradictions documented",
                ]
                checkpoint["required_actions"] = [
                    "Review low-credibility sources",
                    "Verify cross-reference claims",
                    "Resolve or document contradictions",
                ]
            elif phase["name"] == "Synthesis":
                checkpoint["criteria"] = [
                    "All sub-queries addressed",
                    "Sources properly cited",
                    "Conclusions supported by evidence",
                ]
                checkpoint["required_actions"] = [
                    "Verify citation completeness",
                    "Check logical flow",
                    "Validate evidence-conclusion links",
                ]

            checkpoints.append(checkpoint)

        return checkpoints

    def _assess_coordination_risks(
        self, sub_queries: list[dict[str, Any]], dependencies: list[dict[str, Any]]
    ) -> list[str]:
        """Assess potential risks in research coordination."""
        risks = []

        if len(sub_queries) > 10:
            risks.append(
                "High complexity - many sub-queries may lead to information overload"
            )

        if len(dependencies) > len(sub_queries) * 0.3:
            risks.append("High interdependency - delays may cascade through workflow")

        # Check for source availability risks
        temporal_queries = [
            sq for sq in sub_queries if "recent" in sq.get("query", "").lower()
        ]
        if temporal_queries:
            risks.append(
                "Time-sensitive queries - information may become outdated quickly"
            )

        # Check for controversial topics
        controversial_indicators = ["controversial", "debate", "dispute", "opinion"]
        controversial_queries = [
            sq
            for sq in sub_queries
            if any(
                indicator in sq.get("query", "").lower()
                for indicator in controversial_indicators
            )
        ]
        if controversial_queries:
            risks.append("Controversial topics - expect conflicting sources and bias")

        if not risks:
            risks.append("Low risk - straightforward research workflow expected")

        return risks

    def _define_success_criteria(
        self, query: str, _research_strategy: dict[str, Any]
    ) -> list[str]:
        """Define success criteria for the research."""
        criteria = [
            "All sub-queries successfully addressed",
            "Minimum credibility threshold met for all sources",
            "Comprehensive synthesis addressing original query",
            "Proper citations for all claims",
        ]

        # Add specific criteria based on query type
        if "compare" in query.lower() or "versus" in query.lower():
            criteria.append("Fair comparison with balanced source representation")

        if "analysis" in query.lower() or "evaluate" in query.lower():
            criteria.append("Critical analysis with evidence-based conclusions")

        if "recent" in query.lower() or "current" in query.lower():
            criteria.append("Sources from last 12 months for current information")

        return criteria

    def _create_contingency_plans(
        self, _agent_assignments: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[str]]:
        """Create contingency plans for potential issues."""
        return {
            "source_shortage": [
                "Expand search terms and synonyms",
                "Use alternative search engines and databases",
                "Consider related topics and indirect sources",
            ],
            "low_credibility_sources": [
                "Prioritize academic and government sources",
                "Increase search depth for authoritative sources",
                "Consider expert interviews or direct contact",
            ],
            "conflicting_information": [
                "Document all conflicting viewpoints",
                "Seek additional authoritative sources",
                "Present multiple perspectives with credibility assessment",
            ],
            "time_constraints": [
                "Prioritize highest-impact sub-queries",
                "Reduce scope while maintaining quality",
                "Focus on most credible sources only",
            ],
            "agent_failure": [
                "Redistribute tasks to available agents",
                "Simplify complex sub-queries",
                "Use manual fallback procedures",
            ],
        }
