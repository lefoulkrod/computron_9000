"""Code review agent implementation.

This agent takes a single plan step (same schema as the coder agent uses)
and the coder agent's textual output, and decides whether the step appears
implemented correctly. It returns a strict JSON object that conforms to
``CodeReviewResult``.
"""

from __future__ import annotations

from textwrap import dedent

from agents.ollama.coder.context_models import (
    generate_code_review_input_schema_summary,
)
from agents.ollama.sdk import make_run_agent_as_tool_function
from agents.ollama.sdk.schema_tools import model_to_schema
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
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

_CODE_REVIEW_INPUT_SCHEMA = generate_code_review_input_schema_summary()
_REVIEW_SCHEMA = model_to_schema(CodeReviewResult, indent=2, include_docs=True)

NAME = "CODE_REVIEW_AGENT"
DESCRIPTION = "Reviews a single step implementation and returns pass/required_changes."
SYSTEM_PROMPT = dedent(
    f"""
Role: Code Review Agent

Your job is to verify whether a single step in a plan
was implemented correctly based on concrete evidence gathered with tools. You will
be reviewing the output from a coder agent that has implemented the plan step.

You will receive as input
- the plan step that is being implemented
- the detailed list of instructions provided to the coder agent that is used to
  implement the step
- the coder agents summary of what it accomplished
- additional context about the overall plan such as selected tooling

Tools
- exists, is_file, is_dir
- read_file, head, tail, grep, list_dir
- run_bash_cmd for short-lived validations (pytest -q, uvx ruff check ., mypy, grep -R ...)

STRICT OUTPUT
- Return ONLY JSON with this exact shape (no prose, no code fences):
{_REVIEW_SCHEMA}

Verification workflow - you must verify the results of the coder agent do not assume correctness
- Identify acceptance checks from step + instructions: expected files/dirs, symbols,
    strings, config keys, and short commands/tests to run.
- Uses grep, head, tail, and other tools to gather evidence.
- Read relevant files to confirm required content and placements.
- Run short, idempotent commands for validation (tests/lint/type checks) when applicable.
- Run any test steps provided in the list of instructions.
- Decide:
    - success=true when evidence supports the step's goal is met.
    - success=false when evidence is missing or incorrect; list minimal actionable
      fixes in required_changes.
"""
)
TOOLS = [run_bash_cmd, exists, is_dir, is_file, read_file, head, tail, grep, list_dir, save_to_scratchpad, recall_from_scratchpad]

code_review_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
    result_type=CodeReviewResult,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "code_review_agent_tool",
]
