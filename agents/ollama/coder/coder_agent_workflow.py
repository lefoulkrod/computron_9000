"""Workflow orchestration for the coder agent system.

Coordinates requirements/design, strict planning, coding, verification, and review.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TypedDict

from agents.ollama.coder.coder_agent import coder_agent_tool
from agents.ollama.coder.models import PlanStep, ReviewerDecision, VerificationReport
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.reviewer_agent import reviewer_agent_tool
from agents.ollama.coder.system_designer_agent import system_designer_agent_tool
from agents.ollama.coder.verifier_agent import verifier_agent_tool
from config import load_config
from tools.virtual_computer import write_file
from tools.virtual_computer.workspace import set_workspace_folder

logger = logging.getLogger(__name__)


def _update_instructions_on_reject(current: str | None, reviewer_feedback: str) -> str:
    """Append reviewer guidance to step instructions as plain text.

    Args:
        current: Existing instructions string.
        reviewer_feedback: Reviewer guidance to append.

    Returns:
        Updated instruction string with guidance appended.
    """
    base = "" if current is None else str(current)
    guidance = reviewer_feedback.strip()
    joiner = "\n\n" if base else ""
    return f"{base}{joiner}Additional guidance: {guidance}"


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


async def coder_agent_workflow(prompt: str) -> AsyncGenerator[StepYield, None]:
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
    # Persist design
    _ = write_file("DESIGN.md", design_response)

    # Use the planner agent to convert design into an executable plan (JSON)
    plan_prompt = (
        "Create an implementation plan for the software assignment "
        f'"{prompt}" based on the architectural design:\n{design_response}\n'
        "Return only valid JSON list of steps as specified."
    )
    plan_response = await planner_agent_tool(plan_prompt)
    logger.debug("Architect plan response: %s", plan_response)
    plan_steps = _parse_plan(plan_response)
    # Persist plan
    try:
        plan_pretty = json.dumps(json.loads(plan_response), indent=2)
    except json.JSONDecodeError:
        plan_pretty = plan_response
    _ = write_file("PLAN.json", plan_pretty)

    # 2. Loop through steps, coder agent executes, architect agent reviews
    idx = 0
    while idx < len(plan_steps):
        step = plan_steps[idx]
        try:
            # Coder agent executes the plan instructions (tests-first then impl)
            step_input = (
                "Follow these instructions in the headless execution environment. Create tests "
                "listed and run them. Then implement code to pass tests. Keep changes minimal.\n\n"
                f"Step {step.id} - {step.title}: {step.instructions}"
            )
            step_result_msg = await coder_agent_tool(step_input)

            # Verify via VerifierAgent
            # Build a language-agnostic verification prompt from the plan's commands
            verify_prompt = json.dumps(
                {
                    "commands": [c.model_dump() for c in step.commands],
                    "instruction": (
                        "Execute each short-lived verification command in order and return the"
                        " strict JSON summary specified by your system prompt."
                    ),
                }
            )
            verify_response = await verifier_agent_tool(verify_prompt)
            logger.debug("Verifier response: %s", verify_response)
            verification_dict: dict[str, Any] | None = None
            verification: VerificationReport | None = None
            try:
                verification_dict = json.loads(verify_response)
                verification = VerificationReport.model_validate(verification_dict)
            except Exception:
                logger.exception("Failed to parse verifier JSON")
                verification = None

            # Review with strict JSON decision
            review_prompt = json.dumps(
                {
                    "assignment": step.instructions,
                    "result": step_result_msg,
                    "verifier": verification_dict,
                }
            )
            review_response = await reviewer_agent_tool(review_prompt)
            logger.debug("Reviewer response: %s", review_response)
            decision: ReviewerDecision | None = None
            try:
                decision = ReviewerDecision.model_validate(json.loads(review_response))
            except Exception:
                logger.exception("Reviewer did not return valid JSON")
                decision = None

            # Decide advancement
            accepted = bool(
                decision
                and decision.decision == "accepted"
                and verification
                and verification.success
            )

            if accepted:
                idx += 1
                completed = True
            else:
                # Update instructions with must_fixes if present
                if decision and decision.must_fixes:
                    plan_steps[idx].instructions = _update_instructions_on_reject(
                        plan_steps[idx].instructions,
                        "\n".join(decision.must_fixes),
                    )
                completed = False

            # Persist artifacts for this step
            artifacts: list[str] = []
            # Save verification report
            if verification_dict is not None:
                vr_path = f"TEST_REPORT_{step.id}.json"
                _ = write_file(vr_path, json.dumps(verification_dict, indent=2))
                artifacts.append(vr_path)

            yield {
                "step_id": step.id,
                "title": step.title,
                "completed": completed,
                "result": step_result_msg,
                "verification": verification_dict,
            }
        except Exception as exc:
            logger.exception("Coder agent failed on step: %s", step.id)
            msg = f"Failed on step: {step.id}"
            raise CoderWorkflowAgentError(msg) from exc
