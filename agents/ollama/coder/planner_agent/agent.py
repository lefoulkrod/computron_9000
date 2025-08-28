"""Planner agent implementation."""

import logging
from textwrap import dedent

from agents.ollama.coder.planner_agent.models import PlanStep, generate_plan_step_schema_summary
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")

_PLAN_STEP_SCHEMA = generate_plan_step_schema_summary()

PLANNER_SYSTEM_PROMPT = dedent(
    f"""
Role: Implementation Plan Generator

Goal
- Convert the assignment and the designer's JSON into an ordered, executable plan.
- Always begin by initializing the environment.
- Then plan file-by-file implementation using the designer's artifacts.

STRICT OUTPUT
- Return ONLY a JSON array of step objects. No prose, fences, or comments.

Step schema (dynamic from PlanStep):
{_PLAN_STEP_SCHEMA}

Field guidance
- id: "step-1", "step-2", ... (stable ordering)
- title: short imperative phrase
- step_kind: "command" or "file" (single-responsibility)
- command: one short-lived shell command for command steps (omit otherwise)
- file_path: relative path to the file to create/modify for file steps (omit otherwise)
- implementation_details: comprehensive list of precise, code-free requirements derived
    from designer inputs (acceptance_criteria, detailed_requirements, user_stories). This is
    required for file steps and optional for command steps.
- depends_on: prior step ids this step requires (omit if none)

Planning rules
1) Environment first: The first step MUST initialize the environment/tooling based on the
     designer's chosen language and dependency manager.
2) Implementation next:
     - Use the designer's artifacts (names/paths) to choose which file to implement.
     - Honor Artifact.depends_on; dependent artifacts come later in order.
3) One thing per step:
     - Command step: exactly one short-lived, idempotent command (no daemons/watchers/servers).
     - File step: exactly one file (file_path) and a thorough implementation_details list the
         coder can use to fully implement the artifact.
4) No long-running tasks and do not run tests when planning.
5) For implementation_details (especially for file steps), derive from designer inputs:
     - Specify inputs/outputs, data shapes, errors, edge cases, and validation rules.
     - Include contracts/config, public API signatures (names/types only), and I/O behavior.
     - Do NOT include code.
6) Keep paths relative to the workspace. Group tiny related files prudently.

Language-specific tooling guidelines
- Python
    - Env/deps: uv venv; uv sync; uv add/remove; uv lock; uv run; uvx for ephemeral tools.
- JavaScript
    - npm init -y; npm install <pkg>.
- Go
    - go mod init <module>; go get <pkg>; go mod tidy.

Return ONLY the JSON array. No surrounding explanation.
"""
)

planner_agent = Agent(
    name="PLANNER_AGENT",
    description="Creates a detailed, step-by-step implementation plan from a design.",
    instruction=PLANNER_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(planner_agent)
after_model_call_callback = make_log_after_model_call(planner_agent)
planner_agent_tool = make_run_agent_as_tool_function(
    agent=planner_agent,
    tool_description="""
    Turn a high-level design into a structured, JSON implementation plan.
    """,
    # Return raw JSON string; downstream code parses into List[PlanStep]
    result_type=list[PlanStep],
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "planner_agent",
    "planner_agent_tool",
]
