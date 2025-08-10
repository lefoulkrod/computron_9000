"""Workflow orchestration for the coder agent system.

Coordinates system design, planning, coding, and review steps using multiple agents.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel

from agents.ollama.coder.coder_dev_agent import coder_dev_agent_tool
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.reviewer_agent import reviewer_agent_tool
from agents.ollama.coder.system_designer_agent import system_designer_agent_tool
from config import load_config
from tools.virtual_computer import set_working_directory_name

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """Represents a single step in the coder workflow plan.

    Attributes:
        step (Optional[str]): The step identifier or description.
        instructions (Optional[dict[str, Any] | str]): Instructions for the step,
            as a dict or string.
        completed (bool): Whether the step has been completed.
    """

    step: str | None = None
    instructions: dict[str, Any] | str | None = None  # Accepts dict or str for LLM flexibility
    completed: bool = False


class CoderWorkflowAgentError(Exception):
    """Custom exception for coder workflow agent errors."""


class StepYield(TypedDict):
    """Type of items yielded by the workflow generator."""

    step: str | None
    instructions: dict[str, Any] | str | None
    completed: bool
    result: str


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
    set_working_directory_name(workspace_folder)
    return workspace_folder


def _parse_plan(plan_response: str) -> list[PlanStep]:
    """Parse and validate the planner's JSON plan into ``PlanStep`` objects.

    Args:
        plan_response: Raw JSON string from the planner agent.

    Returns:
        list[PlanStep]: Validated list of plan steps.

    Raises:
        CoderWorkflowAgentError: If JSON is invalid or structure is incorrect.
    """
    try:
        plan_data = json.loads(plan_response)
    except json.JSONDecodeError as exc:
        msg = "Failed to parse plan response as JSON"
        logger.exception(msg)
        raise CoderWorkflowAgentError(msg) from exc

    if not isinstance(plan_data, list):
        msg = "Plan response is not a list"
        logger.error("%s: %s", msg, plan_data)
        raise CoderWorkflowAgentError(msg)

    try:
        return [PlanStep.model_validate(step) for step in plan_data]
    except (TypeError, ValueError) as exc:
        msg = "Failed to validate plan response"
        logger.exception(msg)
        raise CoderWorkflowAgentError(msg) from exc


def _update_instructions_on_reject(
    current: dict[str, Any] | str | None,
    reviewer_feedback: str,
) -> dict[str, Any] | str:
    """Augment step instructions with reviewer guidance after rejection.

    Args:
        current: Existing instructions (dict or str).
        reviewer_feedback: The reviewer agent's guidance text.

    Returns:
        dict[str, Any] | str: Updated instructions in the same structure.
    """
    guidance = reviewer_feedback.strip()
    if isinstance(current, dict):
        new_instructions = dict(current)
        new_instructions["additional_instructions"] = guidance
        return new_instructions

    base = "" if current is None else str(current)
    return base + "\n" + f"additional instructions: {guidance}"


async def coder_agent_workflow(
    prompt: str,
) -> AsyncGenerator[StepYield, None]:
    """Main workflow for the coder agent using an architect agent for planning.

    Args:
        prompt (str): The high-level task to accomplish.

    Yields:
    StepYield: Step results and plan updates as the workflow progresses.

    Raises:
        CoderWorkflowAgentError: On unrecoverable errors.
    """
    _create_workspace_dir()
    # Use the system designer agent to create the architecture
    design_prompt = f"Create an architecture design for the software assignment: {prompt}."
    design_response = await system_designer_agent_tool(design_prompt)
    logger.debug("Architect design response: %s", design_response)

    # Use the planner agent to convert design into an executable plan (JSON)
    plan_prompt = (
        "Create an implementation plan for the software assignment "
        f'"{prompt}" based on the architectural design:\n{design_response}\n'
        "Return only valid JSON list of steps as specified."
    )
    plan_response = await planner_agent_tool(plan_prompt)
    logger.debug("Architect plan response: %s", plan_response)
    plan_steps = _parse_plan(plan_response)

    # 2. Loop through steps, coder agent executes, architect agent reviews
    idx = 0
    while idx < len(plan_steps):
        step = plan_steps[idx]
        if step.completed:
            idx += 1
            continue
        try:
            # Coder agent executes the plan instructions
            step_input = f"Execute this coding assignment:{step.instructions}"
            step_result = await coder_dev_agent_tool(step_input)
            plan_steps[idx].completed = True

            # Review the coder agent's work and accept or reject it
            review_prompt = f"assignment: {step.instructions}\nresponse: {step_result}"
            review_response = await reviewer_agent_tool(review_prompt)
            logger.debug("Architect review response: %s", review_response)

            if "accepted" in review_response.lower():
                plan_steps[idx].completed = True
                idx += 1
            elif "rejected" in review_response.lower():
                plan_steps[idx].instructions = _update_instructions_on_reject(
                    plan_steps[idx].instructions,
                    review_response,
                )
                plan_steps[idx].completed = False
                # Do not increment idx, repeat this step
            else:
                logger.warning(
                    "Review response did not contain 'accepted' or 'rejected': %s", review_response
                )
                idx += 1
            item: StepYield = {
                "step": step.step,
                "instructions": step.instructions,
                "completed": step.completed,
                "result": step_result,
            }
            yield item
        except Exception as exc:
            logger.exception("Coder agent failed on step: %s", step.step)
            msg = f"Failed on step: {step.step}"
            raise CoderWorkflowAgentError(msg) from exc
