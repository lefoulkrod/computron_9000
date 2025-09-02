"""Coder-planner agent implementation.

This agent expands a single PlanStep into an ordered, comprehensive list of
concrete implementation sub-steps for the coder agent to execute.
The output is strictly a JSON array of strings (list[str]).
"""

from __future__ import annotations

import logging

from agents.ollama.coder.context_models import (
    generate_coder_planner_input_schema_summary,
)
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)

# Reuse the same strong reasoning/coding-capable model as architect/planner
model = get_model_by_name("coder_architect")

_CODER_PLANNER_INPUT_SCHEMA = generate_coder_planner_input_schema_summary()

CODER_PLANNER_PROMPT = f"""
Role: Expert Implementation Sequencer

Goal: Given a standardized input payload containing the current PlanStep and the
selected project tooling, return a comprehensive, ordered list of exact sub-steps
the Coder agent should take to implement that step.

STRICT OUTPUT
- Return ONLY valid JSON: a single array of strings (list[str]).
- No markdown, comments, code fences, or extra text.

Input payload shape (CoderPlannerInput):
{_CODER_PLANNER_INPUT_SCHEMA}

What to produce
- A precise sequence of actionable steps the Coder should follow.
- Each item must be a short imperative instruction.
- Keep each step atomic (one action per step) and scoped to the provided PlanStep.

Required coverage
- Dependencies: If the PlanStep depends on other artifacts, plan to READ relevant
    files first to understand interfaces and relationships before editing.
- Tests: Include steps to WRITE focused unit tests for the behavior introduced/changed.
- Validation: Include steps to RUN fast validations after implementing (unit tests,
    style/lint checks, type checks if present).
- Files: When creating or editing files, name the exact relative path.
- Commands: When running commands, prefer the project's chosen tooling (e.g., uv run pytest -q).

Constraints
- Do not start servers, watchers, or long-running processes.
- Keep commands short-lived.
- Use only relative paths.
- Do not include code snippets; use descriptions like "implement function X in file Y".

Examples of step phrasing (informal, do not copy verbatim - just get the gist -
use tools appropriate for the language)
- "Read ./src/pkg/module.py to understand Foo API"
- "Create tests/test_module.py with unit tests covering Bar() edge cases"
- "Implement Bar() in ./src/pkg/module.py to meet spec"
- "Run uv run pytest -q and inspect failures"
- "Address failing test assertions in ./src/pkg/module.py"
- "Run uvx ruff check . and uvx black . --check"
- Never read the full contents of lock files or package directories
"""

coder_planner_agent = Agent(
    name="CODER_PLANNER_AGENT",
    description="Expands a planner PlanStep into an ordered list of coder sub-steps (list[str]).",
    instruction=CODER_PLANNER_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(coder_planner_agent)
coder_planner_after_model_call_callback = make_log_after_model_call(coder_planner_agent)

coder_planner_agent_tool = make_run_agent_as_tool_function(
    agent=coder_planner_agent,
    tool_description="""
        Expand the current PlanStep (with tooling context) into a comprehensive, ordered list
        of actionable coder sub-steps. Input is CoderPlannerInput JSON; result is JSON list[str].
        """,
    result_type=list[str],
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[coder_planner_after_model_call_callback],
)

__all__ = [
    "coder_planner_agent",
    "coder_planner_agent_tool",
]
