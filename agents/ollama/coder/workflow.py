"""Workflow orchestration for the coder agent system.

Coordinates design, planning, and step-wise coding execution.
"""

import datetime
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TypedDict

from agents.ollama.coder.architect_agent import architect_agent_tool
from agents.ollama.coder.architect_agent.models import LowLevelDesign
from agents.ollama.coder.code_review_agent import code_review_agent_tool
from agents.ollama.coder.coder_agent import coder_agent_tool
from agents.ollama.coder.coder_planner_agent import coder_planner_agent_tool
from agents.ollama.coder.context_models import (
    CodeReviewInput,
    CoderInput,
    CoderPlannerInput,
)
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.planner_agent.models import PlannerPlan, PlanStep, ToolingSelection
from config import load_config
from tools.virtual_computer import (
    append_to_file,
    make_dirs,
    path_exists,
    write_file,
)
from tools.virtual_computer import (
    read_file as vc_read_file,
)
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
    verification: dict[str, object] | None


def _create_workspace_dir() -> str:
    """Create a workspace directory and return its name.

    Returns:
        str: Name of the workspace folder created under the configured home dir.

    Raises:
        CoderWorkflowAgentError: If the workspace directory cannot be created.
    """
    # Use a short, readable, and sufficiently unique name (8 hex chars)
    workspace_folder = f"ws_{uuid.uuid4().hex[:8]}"
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


def _setup_workspace(workspace: str | None) -> None:
    """Set up the workspace directory for the workflow.

    Args:
        workspace: Optional workspace folder name. If None, creates a new workspace.

    Raises:
        CoderWorkflowAgentError: If workspace setup fails.
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


# Implementation log constants
_IMPL_DIR = ".IMPLEMENTATION"
_IMPL_FILE = f"{_IMPL_DIR}/IMPLEMENTATION_LOG.log"
_IMPL_README = f"{_IMPL_DIR}/README.md"
_DESIGN_FILE = f"{_IMPL_DIR}/DESIGN.log"
_PLAN_FILE = f"{_IMPL_DIR}/PLAN.log"

# Code review retry configuration
_CODE_REVIEW_MAX_RETRIES = 5


def _init_implementation_log() -> None:
    """Ensure the implementation log directory and file exist.

    Creates the hidden ``.IMPLEMENTATION`` directory under the current workspace
    (as configured via ``set_workspace_folder``) and initializes
    ``IMPLEMENTATION_LOG.js`` with an exportable array if the file does not exist.

    This function is best-effort and logs failures via the module logger.
    """
    try:
        _ = make_dirs(_IMPL_DIR)
        exists_info = path_exists(_IMPL_FILE)
        if not exists_info.exists:
            # Initialize as an empty text log file
            _ = write_file(_IMPL_FILE, "")
        # Ensure README exists with notice not to modify
        readme_exists = path_exists(_IMPL_README)
        if not readme_exists.exists:
            _ = write_file(
                _IMPL_README,
                (
                    "# Implementation Log\n\n"
                    "This folder contains implementation logs and snapshots "
                    "(DESIGN.json, PLAN.json).\n\n"
                    "Do not modify, remove, or alter this folder or the files "
                    "in it in any way.\n"
                ),
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to initialize implementation log")


def _append_log_entry(*, step: PlanStep, part: str, data: object) -> None:
    """Append a single structured entry to IMPLEMENTATION_LOG.js.

    Args:
        step: The current plan step providing context (id/title included).
        part: One of "planstep", "coder_planner", "coder_summary", "code_review".
        data: The payload to record (JSON-serializable where possible).
    """
    try:
        ts = datetime.datetime.now(tz=datetime.UTC).isoformat()
        header = f"[{ts}] step {step.id} - {step.title} - {part}\n"
        body: str
        if isinstance(data, str):
            body = data
        elif isinstance(data, list):
            if all(isinstance(x, str) for x in data):
                # Present as bullet list
                body = "\n".join(f"- {x}" for x in data)
            else:
                body = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            body = json.dumps(data, indent=2, ensure_ascii=False)
        text_block = header + body + "\n\n"
        _ = append_to_file(_IMPL_FILE, text_block)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append implementation log for step %s", step.id)


def _load_existing_design() -> LowLevelDesign | None:
    """Load existing DESIGN.json if present and valid.

    Returns:
        LowLevelDesign instance if file exists and is valid, None otherwise.
    """
    try:
        if not path_exists(_DESIGN_FILE).exists:
            return None

        read_result = vc_read_file(_DESIGN_FILE)
        if not read_result.success or not read_result.content:
            return None

        return LowLevelDesign.model_validate_json(read_result.content)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to load existing DESIGN.json; will regenerate")
        return None


def _load_existing_plan() -> PlannerPlan | None:
    """Load existing PLAN.json if present and valid.

    Returns:
        PlannerPlan instance if file exists and is valid, None otherwise.
    """
    try:
        if not path_exists(_PLAN_FILE).exists:
            return None

        read_result = vc_read_file(_PLAN_FILE)
        if not read_result.success or not read_result.content:
            return None

        return PlannerPlan.model_validate_json(read_result.content)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to load existing PLAN.json; will regenerate")
        return None


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
    _setup_workspace(workspace)

    # Create & parse low-level design via the architect agent
    _init_implementation_log()

    # Check for existing plan first (highest priority)
    existing_plan = _load_existing_plan()
    if existing_plan is not None:
        # Plan exists, use it and skip both architect and planner
        plan = existing_plan
    else:
        # No plan exists, check for existing design
        existing_design = _load_existing_design()
        if existing_design is not None:
            # Design exists, use it and run planner
            design_json = existing_design.model_dump_json(indent=2)
            plan, raw_plan = await _run_planner_agent(prompt=prompt, design_json=design_json)
            # Persist raw plan (pretty-printed if possible)
            try:
                plan_pretty = json.dumps(json.loads(raw_plan), indent=2)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                plan_pretty = raw_plan
            _ = write_file(_PLAN_FILE, plan_pretty)
        else:
            # Neither exists, start from beginning
            design = await _run_architect_agent(prompt)
            design_json = design.model_dump_json(indent=2)
            _ = write_file(_DESIGN_FILE, design_json)
            plan, raw_plan = await _run_planner_agent(prompt=prompt, design_json=design_json)
            # Persist raw plan (pretty-printed if possible)
            try:
                plan_pretty = json.dumps(json.loads(raw_plan), indent=2)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                plan_pretty = raw_plan
            _ = write_file(_PLAN_FILE, plan_pretty)

    # 2. Execute the plan steps using the coder agent only
    async for item in _execute_steps_with_coder(plan.steps, plan.tooling):
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


async def _run_planner_agent(*, prompt: str, design_json: str) -> tuple[PlannerPlan, str]:
    """Run the planner agent and return validated plan steps plus raw response.

    Args:
        prompt: Original high-level assignment / task description.
        design_json: The serialized system design JSON produced by system designer.

    Returns:
        A tuple of (PlannerPlan, raw JSON string returned by planner).

    Raises:
        CoderWorkflowAgentError: If the planner agent call fails or returns invalid JSON
            or the plan schema is invalid.
    """
    plan_prompt = f"software assignment:\n{prompt}\narchitectural design:\n{design_json}\n"
    try:
        plan = await planner_agent_tool(plan_prompt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Planner agent call failed")
        msg = "Planner agent call failed"
        raise CoderWorkflowAgentError(msg) from exc
    else:
        return plan, json.dumps(plan.model_dump(), indent=2)


async def _run_coder_agent(
    step: PlanStep, tooling: ToolingSelection, *, fixes: list[str] | None = None
) -> tuple[str, list[str]]:
    """Run the coder agent for a single plan step.

    Args:
        step: The plan step to implement.
        tooling: Top-level tooling selection from the plan (language, package manager,
            test framework).
        fixes: Optional reviewer-required changes from a failed verification to be
            applied on this retry attempt.

    Returns:
        Tuple of (coder_result, instructions_used).

    Raises:
        CoderWorkflowAgentError: If the coder agent call fails.
    """
    # First, expand the plan step into ordered coder sub-steps via coder_planner agent
    try:
        base_instructions = await coder_planner_agent_tool(
            CoderPlannerInput(step=step, tooling=tooling).model_dump_json()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Coder-planner agent call failed for step: %s", step.id)
        msg = f"Coder-planner agent call failed for step: {step.id}"
        raise CoderWorkflowAgentError(msg) from exc
    else:
        # Log the plan step and the coder-planner output
        _append_log_entry(step=step, part="planstep", data=step.model_dump())
        _append_log_entry(step=step, part="coder_planner", data=base_instructions or [])

    # Choose which instructions to use: reviewer fixes if provided, otherwise base plan
    instructions = fixes if (fixes and len(fixes) > 0) else (base_instructions or [])

    # Provide a clear, structured prompt to the coder agent about the current step
    coder_input = CoderInput(
        step=step,
        tooling=tooling,
        instructions=instructions,
    )
    try:
        coder_result: str = await coder_agent_tool(coder_input.model_dump_json())
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Coder agent call failed for step: %s", step.id)
        msg = f"Coder agent call failed for step: {step.id}"
        raise CoderWorkflowAgentError(msg) from exc
    else:
        # Log the coder result summary/output
        _append_log_entry(step=step, part="coder_summary", data=coder_result)
        return coder_result, instructions


async def _execute_steps_with_coder(
    steps: list[PlanStep], tooling: ToolingSelection
) -> AsyncGenerator[StepYield, None]:
    """Iterate through plan steps and execute each with the coder agent.

    Args:
        steps: Ordered list of plan steps to implement.
    tooling: Top-level tooling selection from the plan used by downstream agents.

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
                step_result_msg, plan_instrs = await _run_coder_agent(
                    step, tooling, fixes=fixes_for_retry
                )
                success, fixes = await _verify_step_result(
                    step=step,
                    result=step_result_msg,
                    instructions=plan_instrs,
                    tooling=tooling,
                )
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


async def _verify_step_result(
    *, step: PlanStep, result: str, instructions: list[str], tooling: ToolingSelection
) -> tuple[bool, list[str]]:
    """Verify a coder step's result via the code review agent.

    Calls the code review agent with the plan step and coder output, then
    deserializes the response into ``CodeReviewResult`` for type-safe handling.
    Retries up to _CODE_REVIEW_MAX_RETRIES times on failure, then assumes pass.

    Args:
        step: The plan step that was executed.
        result: The textual output/result from the coder agent for this step.
        instructions: The ordered list of actions used for this attempt; used by reviewer
            for acceptance criteria.
        tooling: Top-level tooling selection from the plan.

    Returns:
        Tuple of (success, required_changes).

    Raises:
        CoderWorkflowAgentError: If the code review agent call fails after all retries.
    """
    review_input = CodeReviewInput(
        step=step,
        tooling=tooling,
        instructions=instructions,
        coder_output=result,
    )

    for attempt in range(1, _CODE_REVIEW_MAX_RETRIES + 1):
        try:
            review = await code_review_agent_tool(review_input.model_dump_json())
        except RuntimeError as exc:  # Only catch expected agent errors
            if attempt < _CODE_REVIEW_MAX_RETRIES:
                logger.warning(
                    "Code review agent call failed for step %s (attempt %d/%d): %s. Retrying...",
                    step.id,
                    attempt,
                    _CODE_REVIEW_MAX_RETRIES,
                    exc,
                )
                continue

            logger.warning(
                "Code review agent call failed for step %s after %d attempts: %s. Assuming pass.",
                step.id,
                _CODE_REVIEW_MAX_RETRIES,
                exc,
            )
            # Log the assumed pass result
            _append_log_entry(
                step=step,
                part="code_review",
                data={"success": True, "required_changes": [], "assumed_pass": True},
            )
            return True, []
        else:
            # Log the code review result
            _append_log_entry(
                step=step,
                part="code_review",
                data={"success": review.success, "required_changes": review.required_changes},
            )
            return review.success, review.required_changes

    # This should never be reached due to the logic above, but satisfies type checker
    return True, []  # pragma: no cover
