"""Agent responsible for producing an actionable implementation plan from a system design.

The step schema is injected dynamically from the `PlanStep` Pydantic model so
prompt stays in sync when fields change (avoids drift).
"""

import logging
from textwrap import dedent

from agents.ollama.coder.models import generate_plan_step_schema_summary
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

    Goal: Convert the assignment + designer's architecture into an execution-ready plan
    focused ONLY on:
    1. Environment & toolchain initialization (ALWAYS the first step)
    2. Dependency / config setup
    3. Creating or updating project files (source, configuration, docs, scaffolding)

    Important exclusions:
        - Do NOT add steps whose primary purpose is writing or running tests
            (those are planned separately)
    - Do NOT include long-running server or watch processes
    - Do NOT include explanatory prose outside the JSON array

    Output: STRICT JSON - an ordered array of step objects (no markdown fences, no trailing text).

    Dynamic step object schema (each element in the JSON array) derived from PlanStep model:
    {_PLAN_STEP_SCHEMA}

    Field meanings (only include those relevant for a given step):
    - id: stable identifier ("step-1", "step-2", ...)
    - title: short imperative phrase
    - instructions: concise description (no code blocks) of work to perform
    - files: list of files to create or modify (omit if none); keep cohesive
    - commands: short-lived, idempotent shell commands (omit if none)
    - acceptance: list of explicit acceptance checks the verifier can later evaluate
    - depends_on: prior step ids this step requires (omit if none)
            - user_stories: list of user stories ("As a <role> I ...") copied verbatim from
                the component(s) in the system design when this step creates/modifies files
                for those components

    Rules:
    1. First step MUST initialize the dev environment and dependency manager.
    2. Prefer single-responsibility steps: either file-focused or command-focused
       unless tightly coupled.
    3. Group tiny related file creations into one step; keep steps small and ordered.
    4. Use only relative paths; never navigate outside workspace.
    5. Prefer deterministic, idempotent commands. No daemons, watchers, or blocking servers.
     6. If a step adds or edits files for a specific component from the design, include that
         component's user_stories in the step's user_stories field (merge if multiple components).
     7. Do NOT execute tests, linters, or type checkers here (only create their
         config files if needed).
     8. Provide acceptance criteria for critical steps (env setup, key scaffolding)
         to aid later verification.
     9. Maintain strict JSON validity: double quotes only, no comments, no dangling commas.

        Language-specific tooling guidelines:
            Python:
                - Use uv for environment + dependency management.
                - Create/sync env: `uv venv` then `uv sync` (after pyproject or lock edits).
                - Add/remove deps: `uv add <pkg>` / `uv remove <pkg>` (updates pyproject + lock).
                - Regenerate lock (explicit): `uv lock`.
                - Run inside env: `uv run <cmd>`.
                - Ephemeral tools: `uvx <tool> [args]`.
                - Tests: uv run pytest (or another test runner) → run tests inside environment.
            JavaScript:
                - Use npm. Init: `npm init -y`. Add: `npm install <pkg>`.
            Go:
                - Use modules. Init: `go mod init <module>`.
                - Manage deps: `go get <pkg>` then `go mod tidy`.
                    Planning:
                        - First step: init env/tooling (uv venv+sync, npm init, or go mod init).
                        - Include only base deps.

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
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
