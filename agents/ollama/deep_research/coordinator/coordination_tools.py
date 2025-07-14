"""
Coordination tools for the Research Coordinator Agent.

This module provides the automated workflow execution tool for the
enhanced task system with centralized task data management.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Import specialized agents for task execution
# NOTE: analysis_tool import kept for future re-enablement
from ..query_decomposition.agent import query_decomposition_tool
from ..shared import (
    AnalysisTaskData,
    QueryDecompositionTaskData,
    SocialResearchTaskData,
    SynthesisTaskData,
    WebResearchTaskData,
    clear_workflow_tasks,
    store_task_data,
)
from ..social_research.agent import social_research_tool
from ..synthesis.agent import synthesis_tool
from ..web_research.agent import web_research_tool

logger = logging.getLogger(__name__)


class DeepResearchWorkflowResponse(BaseModel):
    """Response from executing the automated deep research workflow."""

    success: bool = Field(
        ..., description="Whether the workflow was successfully completed"
    )
    workflow_id: str = Field(..., description="Unique identifier for the workflow")
    final_report: str = Field(..., description="Complete research report")
    research_summary: str = Field(..., description="Executive summary of findings")
    sources_analyzed: int = Field(..., description="Total number of sources analyzed")
    subqueries_processed: int = Field(..., description="Number of subqueries processed")
    execution_time_seconds: float = Field(
        ..., description="Total workflow execution time"
    )
    completion_timestamp: str = Field(..., description="Workflow completion time")


class ErrorResponse(BaseModel):
    """Standard error response format."""

    success: bool = Field(False, description="Always false for error responses")
    error: str = Field(..., description="Error message describing what went wrong")
    error_code: str = Field(..., description="Machine-readable error code")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional error context"
    )


class CoordinationTools:
    """Automated coordination tools for deep research workflows."""

    def __init__(self, agent_id: str) -> None:
        """Initialize coordination tools.

        Args:
            agent_id: Unique identifier for this agent instance.
        """
        self.agent_id = agent_id

    async def execute_deep_research_workflow(
        self,
        research_query: str,
        research_domains: list[str] | None = None,
        output_format: str = "comprehensive_report",
        max_sources: int = 15,
    ) -> str:
        """Execute complete automated deep research workflow.

        This is the single entry point for automated deep research. The workflow
        executes imperatively without LLM decision-making:
        1. Query decomposition
        2. Parallel web and social research
        3. Analysis of research results
        4. Synthesis into final report
        5. Cleanup of task data

        Args:
            research_query: The main research question to investigate
            research_domains: Domains to include (default: ["web", "social"])
            output_format: Format for final report (default: "comprehensive_report")
            max_sources: Maximum sources per research domain (default: 15)

        Returns:
            JSON string containing complete workflow results and final report

        Raises:
            ValueError: If research_query is empty
            RuntimeError: If workflow execution fails
        """
        start_time = datetime.now()

        try:
            # Validate input
            if not research_query or not research_query.strip():
                raise ValueError("research_query cannot be empty")

            if research_domains is None:
                research_domains = ["web", "social"]

            # Generate workflow ID
            workflow_id = f"deep_research_{uuid.uuid4().hex[:8]}"
            logger.info(f"Starting deep research workflow {workflow_id}")

            # Step 1: Query decomposition
            decomp_result = await self._execute_query_decomposition(
                workflow_id, research_query
            )
            subqueries = self._extract_subqueries(decomp_result)
            logger.info(f"Decomposed query into {len(subqueries)} subqueries")

            # Step 2: Parallel research execution
            all_research_results = {}
            total_sources = 0

            if "web" in research_domains:
                web_results = await self._execute_web_research_tasks(
                    workflow_id, subqueries, max_sources
                )
                all_research_results["web_research"] = web_results
                total_sources += self._count_sources(web_results)

            if "social" in research_domains:
                social_results = await self._execute_social_research_tasks(
                    workflow_id, subqueries, max_sources
                )
                all_research_results["social_research"] = social_results
                total_sources += self._count_sources(social_results)

            logger.info(f"Completed research across {len(research_domains)} domains")

            # Step 3: Analysis - TEMPORARILY DISABLED
            # TODO: Re-enable when analysis agent capabilities are enhanced
            # analysis_result = await self._execute_analysis_task(
            #     workflow_id, research_query, all_research_results
            # )
            # logger.info("Completed cross-source analysis")

            # Create empty analysis result for synthesis
            analysis_result = {
                "analysis_summary": "Analysis step temporarily disabled",
                "verification_status": "skipped",
                "credibility_scores": {},
                "inconsistencies": [],
                "recommendations": [],
            }
            logger.info("Skipped analysis step (temporarily disabled)")

            # Step 4: Synthesis
            synthesis_result = await self._execute_synthesis_task(
                workflow_id,
                research_query,
                analysis_result,
                all_research_results,
                output_format,
            )
            logger.info("Completed synthesis")

            # Step 5: Cleanup
            self._cleanup_workflow_tasks(workflow_id)

            # Calculate execution time
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Create response
            response = DeepResearchWorkflowResponse(
                success=True,
                workflow_id=workflow_id,
                final_report=synthesis_result.get("final_report", ""),
                research_summary=synthesis_result.get("executive_summary", ""),
                sources_analyzed=total_sources,
                subqueries_processed=len(subqueries),
                execution_time_seconds=execution_time,
                completion_timestamp=end_time.isoformat(),
            )

            logger.info(
                f"Completed workflow {workflow_id} in {execution_time:.2f} seconds"
            )
            return response.model_dump_json(indent=2)

        except Exception as e:
            logger.error(f"Workflow {workflow_id} failed: {e}")
            # Cleanup on failure
            try:
                self._cleanup_workflow_tasks(workflow_id)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup workflow {workflow_id}: {cleanup_error}"
                )

            error_response = ErrorResponse(
                success=False,
                error=str(e),
                error_code="WORKFLOW_EXECUTION_FAILED",
                context={"workflow_id": workflow_id, "research_query": research_query},
            )
            return error_response.model_dump_json(indent=2)

    def cleanup_completed_tasks(self, workflow_id: str) -> str:
        """Clean up completed tasks for a workflow.

        Args:
            workflow_id: Workflow ID to clean up

        Returns:
            JSON string with cleanup results
        """
        try:
            cleaned_count = clear_workflow_tasks(workflow_id)
            result = {
                "success": True,
                "workflow_id": workflow_id,
                "tasks_cleaned": cleaned_count,
                "message": f"Cleaned up {cleaned_count} tasks for workflow {workflow_id}",
            }
            logger.info(f"Cleaned up {cleaned_count} tasks for workflow {workflow_id}")
            return json.dumps(result, indent=2)

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "workflow_id": workflow_id,
            }
            logger.error(f"Failed to cleanup workflow {workflow_id}: {e}")
            return json.dumps(error_result, indent=2)

    async def _execute_query_decomposition(
        self, workflow_id: str, research_query: str
    ) -> dict[str, Any]:
        """Execute query decomposition task."""
        task_id = f"{workflow_id}_decomp"

        # Create task data
        task_data = QueryDecompositionTaskData(
            task_id=task_id,
            workflow_id=workflow_id,
            original_query=research_query,
            max_subqueries=5,
            decomposition_strategy="comprehensive",
            created_at=datetime.now().isoformat(),
        )

        # Store task data
        store_task_data(task_data)

        # Execute agent with task ID
        return await self._execute_agent_with_task("query_decomposition", task_id)

    async def _execute_web_research_tasks(
        self, workflow_id: str, subqueries: list[str], max_sources: int
    ) -> dict[str, Any]:
        """Execute web research tasks for all subqueries."""
        results = {}

        for i, subquery in enumerate(subqueries):
            task_id = f"{workflow_id}_web_{i}"

            # Create task data
            task_data = WebResearchTaskData(
                task_id=task_id,
                workflow_id=workflow_id,
                search_query=subquery,
                max_sources=max_sources // len(subqueries),
                search_depth="comprehensive",
                created_at=datetime.now().isoformat(),
            )

            # Store task data
            store_task_data(task_data)

            # Execute agent
            result = await self._execute_agent_with_task("web_research", task_id)
            results[f"subquery_{i}"] = result

        return results

    async def _execute_social_research_tasks(
        self, workflow_id: str, subqueries: list[str], max_sources: int
    ) -> dict[str, Any]:
        """Execute social research tasks for all subqueries."""
        results = {}

        for i, subquery in enumerate(subqueries):
            task_id = f"{workflow_id}_social_{i}"

            # Create task data
            task_data = SocialResearchTaskData(
                task_id=task_id,
                workflow_id=workflow_id,
                search_query=subquery,
                max_posts=max_sources // len(subqueries),
                platforms=["reddit"],
                created_at=datetime.now().isoformat(),
            )

            # Store task data
            store_task_data(task_data)

            # Execute agent
            result = await self._execute_agent_with_task("social_research", task_id)
            results[f"subquery_{i}"] = result

        return results

    async def _execute_analysis_task(
        self, workflow_id: str, original_query: str, research_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute analysis task."""
        task_id = f"{workflow_id}_analysis"

        # Create task data
        task_data = AnalysisTaskData(
            task_id=task_id,
            workflow_id=workflow_id,
            original_query=original_query,
            research_results=research_results,
            analysis_type="comprehensive",
            cross_verification=True,
            created_at=datetime.now().isoformat(),
        )

        # Store task data
        store_task_data(task_data)

        # Execute agent
        return await self._execute_agent_with_task("analysis", task_id)

    async def _execute_synthesis_task(
        self,
        workflow_id: str,
        original_query: str,
        analysis_results: dict[str, Any],
        research_findings: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        """Execute synthesis task."""
        task_id = f"{workflow_id}_synthesis"

        # Create task data
        task_data = SynthesisTaskData(
            task_id=task_id,
            workflow_id=workflow_id,
            original_query=original_query,
            analysis_results=analysis_results,
            research_findings=research_findings,
            output_format=output_format,
            include_citations=True,
            created_at=datetime.now().isoformat(),
        )

        # Store task data
        store_task_data(task_data)

        # Execute agent
        return await self._execute_agent_with_task("synthesis", task_id)

    async def _execute_agent_with_task(
        self, agent_type: str, task_id: str
    ) -> dict[str, Any]:
        """Execute an agent with the specified task ID."""
        try:
            logger.info(f"Executing {agent_type} agent with task {task_id}")

            result_raw: Any
            if agent_type == "query_decomposition":
                result_raw = await query_decomposition_tool(task_id)
            elif agent_type == "web_research":
                result_raw = await web_research_tool(task_id)
            elif agent_type == "social_research":
                result_raw = await social_research_tool(task_id)
            elif agent_type == "analysis":
                # Analysis agent temporarily disabled
                logger.warning("Analysis agent called but temporarily disabled")
                return {
                    "analysis_summary": "Analysis step temporarily disabled",
                    "verification_status": "skipped",
                    "credibility_scores": {},
                    "inconsistencies": [],
                    "recommendations": [],
                }
                # result_raw = await analysis_tool(task_id)  # Commented out
            elif agent_type == "synthesis":
                result_raw = await synthesis_tool(task_id)
            else:
                raise ValueError(f"Unsupported agent type: {agent_type}")

            # Parse result if it's a JSON string
            result: dict[str, Any]
            if isinstance(result_raw, str):
                try:
                    parsed_result = json.loads(result_raw)
                    result = parsed_result
                except json.JSONDecodeError:
                    # If it's not valid JSON, wrap it
                    result = {"raw_result": result_raw}
            elif isinstance(result_raw, dict):
                result = result_raw
            else:
                # Ensure we always return a dict
                result = {"result": result_raw}

            logger.info(f"Completed {agent_type} task {task_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to execute {agent_type} task {task_id}: {e}")
            raise RuntimeError(f"Agent execution failed: {e}") from e

    def _extract_subqueries(self, decomp_result: dict[str, Any]) -> list[str]:
        """Extract subqueries from decomposition result."""
        try:
            subqueries: list[str] = []

            # Handle different possible result structures
            if "subqueries" in decomp_result:
                raw_subqueries = decomp_result["subqueries"]
            elif "sub_queries" in decomp_result:
                raw_subqueries = decomp_result["sub_queries"]
            elif "queries" in decomp_result:
                raw_subqueries = decomp_result["queries"]
            else:
                # Fallback: look for list structures
                raw_subqueries = None
                for value in decomp_result.values():
                    if isinstance(value, list) and len(value) > 0:
                        if isinstance(value[0], str):
                            raw_subqueries = value
                            break
                        if isinstance(value[0], dict) and "query" in value[0]:
                            raw_subqueries = [item["query"] for item in value]
                            break

                if raw_subqueries is None:
                    raise ValueError(
                        "Could not extract subqueries from decomposition result"
                    )

            # Ensure we have strings
            if isinstance(raw_subqueries, list) and len(raw_subqueries) > 0:
                if isinstance(raw_subqueries[0], dict):
                    subqueries = [
                        q.get("query", q.get("text", str(q))) for q in raw_subqueries
                    ]
                else:
                    subqueries = [str(q) for q in raw_subqueries]
            else:
                subqueries = []

            return subqueries[:5]  # Limit to 5 subqueries

        except Exception as e:
            logger.error(f"Failed to extract subqueries: {e}")
            # Fallback to original query if decomposition parsing fails
            original_query = decomp_result.get("original_query", "research query")
            return [str(original_query)]

    def _count_sources(self, research_results: dict[str, Any]) -> int:
        """Count total sources in research results."""
        total = 0
        for result in research_results.values():
            if isinstance(result, dict):
                # Look for common source count fields
                if "sources_count" in result:
                    total += result["sources_count"]
                elif "total_sources" in result:
                    total += result["total_sources"]
                elif "sources" in result:
                    if isinstance(result["sources"], list):
                        total += len(result["sources"])
                elif "source_count" in result:
                    total += result["source_count"]
        return total

    def _cleanup_workflow_tasks(self, workflow_id: str) -> None:
        """Clean up all tasks for a workflow."""
        try:
            cleared_count = clear_workflow_tasks(workflow_id)
            logger.info(f"Cleaned up {cleared_count} tasks for workflow {workflow_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup workflow {workflow_id}: {e}")

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()
