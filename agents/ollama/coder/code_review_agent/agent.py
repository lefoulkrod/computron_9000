"""Code review agent implementation.

This agent takes a single plan step (same schema as the coder agent uses)
and the coder agent's textual output, and decides whether the step appears
implemented correctly. It returns a strict JSON object that conforms to
``CodeReviewResult``.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.coder.planner_agent.models import generate_plan_step_schema_summary
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name
from tools.virtual_computer import (
    exists,
    grep,
    head,
    is_dir,
    is_file,
    list_dir,
    read_file,
    run_bash_cmd,
    tail,
)

from .models import CodeReviewResult

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")

_PLAN_STEP_SCHEMA = generate_plan_step_schema_summary()
_REVIEW_SCHEMA = '{\n    "success": "boolean",\n    "required_changes": ["string", "..."]\n}'

SYSTEM_PROMPT = dedent(
    f"""
Role: Code Review Agent

Goal
- Given a single implementation plan step and the coder agent's textual output,
  determine if the step was implemented correctly in the workspace.

Inputs
- step: JSON object matching the PlanStep schema
- coder_output: string summarizing what the coder agent did

Tools you can and should use
- path_exists: Check whether a file or directory exists.
- read_file: Read text files with optional line range support.
- list_dir: List directory contents with optional hidden file filtering.
- run_bash_cmd: Run read-only shell commands to validate outcomes (e.g., grep, pytest,
  mypy, ruff, build/test commands specified by the step). Prefer idempotent, non-mutating
  commands.

STRICT OUTPUT
- Return ONLY a JSON object with this exact shape (no prose, no code fences):
{_REVIEW_SCHEMA}

Interpretation rules
1) Prefer evidence gathered via tools over statements in coder_output. Use the tools above to
    verify that files/dirs exist, expected content is present, and specified
    commands/tests succeed.
2) If the step's intended outcome is fully and correctly implemented (supported by actual evidence),
    set "success" to true. Minor deviations that do not affect the step's goal can still succeed.
3) If evidence is insufficient or the implementation appears incomplete/incorrect,
    set "success" to false and enumerate concise, actionable fixes in "required_changes".
    Prioritize minimal changes to complete the step.
4) Never include explanations outside the JSON. Always return the exact structure.

Verification workflow (guidance)
- Parse the step to identify concrete acceptance checks: target files/dirs, key symbols
    or text expected in files, commands/tests that should run, and any API or schema changes.
- Use path_exists to confirm presence of expected files/dirs.
- Use read_file and list_dir to inspect relevant files; verify required symbols,
    config keys, strings, or code fragments exist and appear in the correct locations.
- Use run_bash_cmd for read-only verification (e.g., `pytest -q -k <pattern>`,
    `grep -R "symbol" path`, `python -m module --help`). Avoid mutating the workspace
    unless the step explicitly required it.
- Base your pass/fail solely on observed evidence. If anything is ambiguous,
    prefer fail with minimal required changes.

Schemas for reference
PlanStep:
{_PLAN_STEP_SCHEMA}
"""
)

code_review_agent = Agent(
    name="CODE_REVIEW_AGENT",
    description="Reviews a single step implementation and returns pass/required_changes.",
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[run_bash_cmd, exists, is_dir, is_file, read_file, head, tail, grep, list_dir],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(code_review_agent)
after_model_call_callback = make_log_after_model_call(code_review_agent)
code_review_agent_tool = make_run_agent_as_tool_function(
    agent=code_review_agent,
    tool_description=(
        "Given a plan step and coder output, decide if it passes and provide required_changes if not."
    ),
    result_type=CodeReviewResult,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "code_review_agent",
    "code_review_agent_tool",
]
