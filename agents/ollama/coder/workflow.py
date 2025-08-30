"""Workflow orchestration for the coder agent system.

Coordinates design, planning, and step-wise coding execution.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TypedDict

from agents.ollama.coder.architect_agent import architect_agent_tool
from agents.ollama.coder.architect_agent.models import LowLevelDesign
from agents.ollama.coder.code_review_agent import code_review_agent_tool
from agents.ollama.coder.coder_agent import coder_agent_tool
from agents.ollama.coder.coder_planner_agent import coder_planner_agent_tool
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.planner_agent.models import PlanStep
from config import load_config
from tools.virtual_computer import write_file
from tools.virtual_computer.workspace import set_workspace_folder

logger = logging.getLogger(__name__)


class CoderWorkflowAgentError(Exception):
    """Custom exception for coder workflow agent errors."""


class StepYield(TypedDict):
    """Items yielded by the workflow generator."""

    step_id: str
    title: str
    completed: bool
    result: str
    verification: dict[str, Any] | None


def _create_workspace_dir() -> str:
    """Create a workspace directory and return its name.

    Returns:
        str: Name of the workspace folder created under the configured home dir.

    Raises:
        CoderWorkflowAgentError: If the workspace directory cannot be created.
    """
    workspace_folder = f"folder_{uuid.uuid4().hex}"
    config = load_config()
    home_dir = config.virtual_computer.home_dir
    workspace_path = Path(home_dir) / workspace_folder
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.exception("Failed to create workspace directory: %s", workspace_path)
        msg = f"Failed to create workspace directory: {workspace_path}"
        raise CoderWorkflowAgentError(msg) from exc
    set_workspace_folder(workspace_folder)
    return workspace_folder


async def workflow(prompt: str, workspace: str | None = None) -> AsyncGenerator[StepYield, None]:
    """Main workflow for the coder agent using an architect agent for planning.

    Args:
        prompt (str): The high-level task to accomplish.
        workspace (str | None): Optional workspace folder name. If None, creates a new workspace.

    Yields:
        StepYield: Step results and plan updates as the workflow progresses.

    Raises:
        CoderWorkflowAgentError: On unrecoverable errors.
    """
    if workspace is None:
        _create_workspace_dir()
    else:
        # Use the provided workspace folder and ensure it exists
        config = load_config()
        home_dir = config.virtual_computer.home_dir
        workspace_path = Path(home_dir) / workspace
        try:
            workspace_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.exception("Failed to create/access workspace directory: %s", workspace_path)
            msg = f"Failed to create/access workspace directory: {workspace_path}"
            raise CoderWorkflowAgentError(msg) from exc
        set_workspace_folder(workspace)

    # Create & parse low-level design via the architect agent
    design = await _run_architect_agent(prompt)
    design_json = design.model_dump_json(indent=2)
    _ = write_file("DESIGN.json", design_json)

    # Use the planner agent via wrapper to convert design into an executable plan (JSON)
    plan_steps, raw_plan = await _run_planner_agent(prompt=prompt, design_json=design_json)
    # Persist raw plan (pretty-printed if possible)
    try:
        plan_pretty = json.dumps(json.loads(raw_plan), indent=2)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        plan_pretty = raw_plan
    _ = write_file("PLAN.json", plan_pretty)

    # 2. Execute the plan steps using the coder agent only
    async for item in _execute_steps_with_coder(plan_steps):
        yield item


async def _run_architect_agent(task_prompt: str) -> LowLevelDesign:
    """Run the architect agent and deserialize JSON into ``LowLevelDesign``.

    Args:
        task_prompt: High-level user assignment / problem statement.

    Returns:
    Parsed ``LowLevelDesign`` instance.

    Raises:
    CoderWorkflowAgentError: If the agent output is not valid JSON or fails validation.
    """
    try:
        return await architect_agent_tool(task_prompt)
    except Exception as exc:  # pragma: no cover - defensive, underlying lib may raise generic
        logger.exception("Architect agent call failed")
        msg = "Architect agent call failed"
        raise CoderWorkflowAgentError(msg) from exc


async def _run_planner_agent(*, prompt: str, design_json: str) -> tuple[list[PlanStep], str]:
    """Run the planner agent and return validated plan steps plus raw response.

    Args:
        prompt: Original high-level assignment / task description.
        design_json: The serialized system design JSON produced by system designer.

    Returns:
        A tuple of (list[PlanStep], raw JSON string returned by planner).

    Raises:
        CoderWorkflowAgentError: If the planner agent call fails or returns invalid JSON
            or the plan schema is invalid.
    """
    plan_prompt = f"software assignment:\n{prompt}\narchitectural design:\n{design_json}\n"
    try:
        plan_steps = await planner_agent_tool(plan_prompt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Planner agent call failed")
        msg = "Planner agent call failed"
        raise CoderWorkflowAgentError(msg) from exc
    else:
        return plan_steps, json.dumps([s.model_dump() for s in plan_steps], indent=2)


def _collect_step_dependencies(
    *, steps_by_id: dict[str, PlanStep], start: PlanStep
) -> list[PlanStep]:
    """Collect transitive dependencies for a step.

    Performs a DFS over ``depends_on`` to gather all reachable dependency steps,
    preserving a stable order by first-seen during traversal. Cycles are
    guarded against via a visited set.

    Args:
        steps_by_id: Mapping of step id to ``PlanStep``.
        start: The step whose dependencies to collect.

    Returns:
        A list of dependency steps. Missing ids are ignored but logged.
    """
    ordered: list[PlanStep] = []
    visited: set[str] = set()

    def dfs(step_id: str) -> None:
        if step_id in visited:
            return
        visited.add(step_id)
        dep = steps_by_id.get(step_id)
        if dep is None:
            logger.warning("Unknown dependency step id: %s", step_id)
            return
        # Traverse its deps first
        for nxt in dep.depends_on:
            dfs(nxt)
        ordered.append(dep)

    for dep_id in start.depends_on:
        dfs(dep_id)
    return ordered


async def _run_coder_agent(step: PlanStep, *, fixes: list[str] | None = None) -> str:
    """Run the coder agent for a single plan step.

    Args:
        step: The plan step to implement.
        dependencies: Other steps this step depends on (transitive closure),
            ordered approximately by dependency depth.
        fixes: Optional reviewer-required changes from a failed verification,
            to be applied on this retry attempt.

    Returns:
        The coder agent's textual result/output for the step.

    Raises:
        CoderWorkflowAgentError: If the coder agent call fails.
    """
    # First, expand the plan step into ordered coder sub-steps via coder_planner agent
    try:
        planner_instructions = await coder_planner_agent_tool(
            json.dumps(
                {
                    "step": step.model_dump(),
                    "instructions": (
                        "Expand this PlanStep into an ordered list of concrete coder sub-steps."
                    ),
                }
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Coder-planner agent call failed for step: %s", step.id)
        msg = f"Coder-planner agent call failed for step: {step.id}"
        raise CoderWorkflowAgentError(msg) from exc

    # Provide a clear, structured prompt to the coder agent about the current step
    step_payload: dict[str, Any] = {
        "step": step.model_dump(),
        # Join list[str] into a single plain-text instruction block
        "instructions": "\n".join(planner_instructions or []),
    }
    if fixes:
        # Provide reviewer-required fixes to guide the retry implementation.
        step_payload["fixes"] = fixes
    try:
        # Send as formatted JSON string to preserve structure
        return await coder_agent_tool(json.dumps(step_payload))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Coder agent call failed for step: %s", step.id)
        msg = f"Coder agent call failed for step: {step.id}"
        raise CoderWorkflowAgentError(msg) from exc


async def _execute_steps_with_coder(steps: list[PlanStep]) -> AsyncGenerator[StepYield, None]:
    """Iterate through plan steps and execute each with the coder agent.

    Args:
        steps: Ordered list of plan steps to implement.

    Yields:
        StepYield dictionaries containing per-step results.

    Notes:
        We loop and re-run the coder step until verification passes. When verification
        fails, its required changes ("fixes") are passed into the next retry.
    """
    for step in steps:
        try:
            # Execute steps strictly in the provided order; do not collect or pass
            # transitive dependencies. Each step is handled independently.
            attempt = 0
            fixes_for_retry: list[str] | None = None
            while True:
                attempt += 1
                logger.info("Executing step %s (attempt %s)", step.id, attempt)
                step_result_msg = await _run_coder_agent(step, fixes=fixes_for_retry)
                success, fixes = await _verify_step_result(step=step, result=step_result_msg)
                if success:
                    logger.info("Step %s passed verification on attempt %s", step.id, attempt)
                    yield {
                        "step_id": step.id,
                        "title": step.title,
                        "completed": True,
                        "result": step_result_msg,
                        "verification": {"success": True, "required_changes": fixes},
                    }
                    break
                logger.warning(
                    "Verification failed for step %s on attempt %s; retrying",
                    step.id,
                    attempt,
                )
                # On failure, carry the fixes into the next retry attempt.
                fixes_for_retry = fixes or None
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Coder agent failed on step: %s", step.id)
            msg = f"Failed on step: {step.id}"
            raise CoderWorkflowAgentError(msg) from exc


async def _verify_step_result(*, step: PlanStep, result: str) -> tuple[bool, list[str]]:
    """Verify a coder step's result via the code review agent.

    Calls the code review agent with the plan step and coder output, then
    deserializes the response into ``CodeReviewResult`` for type-safe handling.

    Args:
        step: The plan step that was executed.
        result: The textual output/result from the coder agent for this step.

    Returns:
        Tuple of (success, required_changes).

    Raises:
        CoderWorkflowAgentError: If the code review agent call fails.
    """
    payload = {"step": step.model_dump(), "coder_output": result}
    try:
        review = await code_review_agent_tool(json.dumps(payload))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Code review agent call failed for step: %s", step.id)
        msg = f"Code review agent call failed for step: {step.id}"
        raise CoderWorkflowAgentError(msg) from exc
    else:
        return review.success, review.required_changes
