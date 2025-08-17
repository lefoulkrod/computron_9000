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
from agents.ollama.coder.models import (
    PlanStep,
    QATestPlan,
    VerificationReport,
    VerifierDecision,
)
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.system_design_models import SystemDesign
from agents.ollama.coder.system_designer_agent import system_designer_agent_tool
from agents.ollama.coder.test_executor_agent import test_executor_agent_tool
from agents.ollama.coder.test_planner_agent import test_planner_agent_tool
from agents.ollama.coder.verifier_agent import verifier_agent_tool
from config import load_config
from tools.virtual_computer import write_file
from tools.virtual_computer.workspace import set_workspace_folder

logger = logging.getLogger(__name__)


def _augment_instructions_on_failure(current: str | None, notes: str) -> str:
    """Append failure guidance (e.g., from failed verification) to instructions.

    Args:
        current: Existing instructions text.
        notes: Guidance to append detailing fixes required.

    Returns:
        Updated instructions string.
    """
    base = "" if current is None else str(current)
    guidance = notes.strip()
    joiner = "\n\n" if base else ""
    return f"{base}{joiner}Fix guidance: {guidance}"


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


async def workflow(prompt: str) -> AsyncGenerator[StepYield, None]:
    """Main workflow for the coder agent using an architect agent for planning.

    Args:
        prompt (str): The high-level task to accomplish.

    Yields:
    StepYield: Step results and plan updates as the workflow progresses.

    Raises:
        CoderWorkflowAgentError: On unrecoverable errors.
    """
    _create_workspace_dir()

    # Create & parse system design
    design = await _run_system_designer_agent(prompt)
    try:
        design_json = design.model_dump_json(indent=2)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        design_json = json.dumps(design.model_dump(), indent=2)
    _ = write_file("DESIGN.json", design_json)

    # Use the planner agent to convert design into an executable plan (JSON)
    plan_prompt = (
        "Create an implementation plan for the software assignment "
        f'"{prompt}" based on the architectural design:\n{design_json}\n'
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

    # 2. Loop through steps:
    #    coder executes -> test planner generates plan -> test executor runs commands
    #    -> gating verifier decides
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
            # Test planner produces test plan
            plan_prompt_payload = json.dumps(
                {"assignment": step.instructions, "coder_output": step_result_msg}
            )
            tp_response = await test_planner_agent_tool(plan_prompt_payload)
            logger.debug("Test planner response: %s", tp_response)
            tp_plan: QATestPlan | None = None
            tp_plan_dict: dict[str, Any] | None = None
            try:
                tp_plan_dict = json.loads(tp_response)
                tp_plan = QATestPlan.model_validate(tp_plan_dict)
            except Exception:
                logger.exception("Test planner did not return valid JSON plan")
                tp_plan = None

            # Commands for test executor
            if tp_plan and tp_plan.commands:
                exec_commands = [c.model_dump() for c in tp_plan.commands]
            else:
                exec_commands = [c.model_dump() for c in step.commands]

            exec_prompt = json.dumps({"commands": exec_commands})
            exec_response = await test_executor_agent_tool(exec_prompt)
            logger.debug("Test executor response: %s", exec_response)
            execution_dict: dict[str, Any] | None = None
            execution: VerificationReport | None = None
            try:
                execution_dict = json.loads(exec_response)
                execution = VerificationReport.model_validate(execution_dict)
            except Exception:
                logger.exception("Failed to parse test executor JSON")
                execution = None

            # Gating verifier decision
            gate_payload = json.dumps(
                {
                    "assignment": step.instructions,
                    "coder_output": step_result_msg,
                    "test_plan": tp_plan_dict,
                    "execution_report": execution_dict,
                }
            )
            gate_response = await verifier_agent_tool(gate_payload)
            logger.debug("Gating verifier response: %s", gate_response)
            decision: VerifierDecision | None = None
            try:
                decision = VerifierDecision.model_validate(json.loads(gate_response))
            except Exception:
                logger.exception("Verifier did not return valid decision JSON")
                decision = None

            accepted = bool(decision and decision.accepted and execution and execution.success)
            if accepted:
                idx += 1
                completed = True
            else:
                guidance = "Step failed verification; improve implementation/tests."
                if decision and decision.fixes:
                    guidance = "\n".join(decision.fixes)
                plan_steps[idx].instructions = _augment_instructions_on_failure(
                    plan_steps[idx].instructions, guidance
                )
                completed = False

            # Persist artifacts for this step
            artifacts: list[str] = []
            # Save verification report
            if execution_dict is not None:
                er_path = f"TEST_EXEC_REPORT_{step.id}.json"
                _ = write_file(er_path, json.dumps(execution_dict, indent=2))
                artifacts.append(er_path)
            if tp_plan_dict is not None:
                tp_path = f"TEST_PLAN_{step.id}.json"
                _ = write_file(tp_path, json.dumps(tp_plan_dict, indent=2))
                artifacts.append(tp_path)

            yield {
                "step_id": step.id,
                "title": step.title,
                "completed": completed,
                "result": step_result_msg,
                "verification": execution_dict,
            }
        except Exception as exc:
            logger.exception("Coder agent failed on step: %s", step.id)
            msg = f"Failed on step: {step.id}"
            raise CoderWorkflowAgentError(msg) from exc


async def _run_system_designer_agent(task_prompt: str) -> SystemDesign:
    """Run the system designer agent and deserialize JSON into ``SystemDesign``.

    Args:
        task_prompt: High-level user assignment / problem statement.

    Returns:
        Parsed ``SystemDesign`` instance.

    Raises:
        CoderWorkflowAgentError: If the agent output is not valid JSON or fails validation.
    """
    try:
        raw = await system_designer_agent_tool(task_prompt)
    except Exception as exc:  # pragma: no cover - defensive, underlying lib may raise generic
        logger.exception("System designer agent call failed")
        msg = "System designer agent call failed"
        raise CoderWorkflowAgentError(msg) from exc
    logger.debug("Raw system design JSON: %s", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.exception("System designer returned non-JSON output")
        msg = "System designer did not return valid JSON"
        raise CoderWorkflowAgentError(msg) from exc
    try:
        return SystemDesign.model_validate(data)
    except Exception as exc:
        logger.exception("System design JSON failed validation")
        msg = "Invalid system design JSON structure"
        raise CoderWorkflowAgentError(msg) from exc
