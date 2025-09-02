"""Code review agent implementation.

This agent takes a single plan step (same schema as the coder agent uses)
and the coder agent's textual output, and decides whether the step appears
implemented correctly. It returns a strict JSON object that conforms to
``CodeReviewResult``.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.coder.context_models import (
    generate_code_review_input_schema_summary,
)
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.ollama.sdk.schema_tools import model_to_schema
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

_CODE_REVIEW_INPUT_SCHEMA = generate_code_review_input_schema_summary()
# Generate strict JSON example from the actual Pydantic model
_REVIEW_SCHEMA = model_to_schema(CodeReviewResult, indent=2, include_docs=True)

SYSTEM_PROMPT = dedent(
    f"""
        There is no `search` tool. Use `grep` instead.
Role: Code Review Agent

You operate in a headless virtual computer. Your job is to verify whether a single plan step
was implemented correctly based on concrete evidence gathered with tools.

Input JSON payload (CodeReviewInput)
{_CODE_REVIEW_INPUT_SCHEMA}

Tools (read-only)
- exists, is_file, is_dir
- read_file, head, tail, grep, list_dir
- run_bash_cmd for short-lived validations (pytest -q, uvx ruff check ., mypy, grep -R ...)

STRICT OUTPUT
- Return ONLY JSON with this exact shape (no prose, no code fences):
{_REVIEW_SCHEMA}

Verification workflow (guidance)
- Identify acceptance checks from step + planner_instructions: expected files/dirs, symbols,
    strings, config keys, and short commands/tests to run.
- Use path checks and directory listings to confirm presence.
- Read relevant files to confirm required content and placements.
- Run short, idempotent commands for validation (tests/lint/type checks) when applicable.
- Decide:
    - success=true when evidence supports the step's goal is met.
    - success=false when evidence is missing or incorrect; list minimal actionable
      fixes in required_changes.
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
        "Given standardized context (CodeReviewInput), decide if the step passes and provide"
        " required_changes if not."
    ),
    result_type=CodeReviewResult,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "code_review_agent",
    "code_review_agent_tool",
]
