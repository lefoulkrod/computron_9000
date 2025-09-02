"""Planner agent implementation."""

import logging

from agents.ollama.coder.planner_agent.models import (
    PlannerPlan,
    generate_planner_plan_schema_summary,
)
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")

_PLAN_SCHEMA = generate_planner_plan_schema_summary()

PLANNER_SYSTEM_PROMPT = f"""
Role: Expert Implementation Planner

Goal: Transform the software assignment and the architect's JSON design into a clear,
step-by-step plan that an autonomous developer can follow.

STRICT OUTPUT
- Return ONLY valid JSON: a single object with top-level keys "tooling" and "steps".
- No markdown, comments, code fences, or extra text.

Schema summary:
{_PLAN_SCHEMA}

Guidelines
- Populate the tooling section by selecting the programming language,
  package manager, and test framework.
- Step 1 MUST initialize the project environment with the chosen tooling.
- Order artifacts so that items without dependencies come before dependent ones.
- Each step performs exactly one short command or one file creation/modification.
- Derive implementation_details from the architect's design and assignment, listing
  precise requirements without code.
- Avoid long-running commands, servers, or watchers.
- Final step MUST add a README explaining how to install dependencies, run the app,
  and execute tests.
- Use relative paths and depends_on where necessary.\

Downstream context expectations
- Each coder-related agent will receive the current plan step and the top-level tooling.
- Ensure each PlanStep has enough implementation_details for a coder to act.

Language-specific tooling guidelines
- Python
        - Environment and deps: uv venv; uv sync; uv add <pkg>; uv add --dev <pkg>;
            uv remove <pkg>; uv lock; uv run <cmd>; uvx <tool> for ephemeral CLIs.
    - Testing: prefer pytest (uv add --dev pytest); run with uv run pytest -q.
        - Lint/format: prefer ruff and black (uv add --dev ruff black);
            run with uvx ruff check . and uvx black .
- JavaScript
    - Project init: npm init -y.
    - Deps: npm install <pkg>; dev deps: npm install -D <pkg>.
    - TypeScript (if chosen): npm install -D typescript ts-node @types/node; npx tsc --init.
    - Testing: prefer vitest or jest (npm install -D vitest); run once with npx vitest run.
        - Lint/format (optional): npm install -D eslint prettier;
            run with npx eslint . and npx prettier --check .
- Go
    - Modules and deps: go mod init <module>; go get <pkg>; go mod tidy.
    - Testing: go test ./... -v.
    - Build/run: go run ./cmd/<app> or go build -o bin/<app> ./cmd/<app>.
"""

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
    Turn a high-level design into a structured, JSON implementation plan containing
    top-level tooling and an ordered list of steps.
    """,
    # Return structured PlannerPlan; downstream code extracts steps
    result_type=PlannerPlan,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "planner_agent",
    "planner_agent_tool",
]
