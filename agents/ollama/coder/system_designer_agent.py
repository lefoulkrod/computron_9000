"""Agent responsible for producing the system architecture/design for a coding task."""

import logging

from agents.ollama.coder.system_design_models import generate_schema_summary
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


# Use the architect model for system design tasks
model = get_model_by_name("coder_architect")


_SCHEMA_SUMMARY = generate_schema_summary()

SYSTEM_DESIGN_PROMPT = f"""
Role: Expert Software Architect

Goal: Produce a comprehensive structured system design for a software assignment that downstream
agents (planner, implementer, tester) can consume programmatically.

STRICT OUTPUT: Return ONLY valid JSON matching the SystemDesign schema below. No markdown, no
explanatory prose outside JSON. Do not add comments. Do not wrap in code fences.

Schema (types) summary:
{_SCHEMA_SUMMARY}

Requirements & Guidance:
- You MUST pick and justify exactly one primary programming language.
- You MUST pick exactly one dependency manager appropriate
    for the language (Python: uv or poetry; Node.js: pnpm or npm; Rust: cargo; Go: go-mod).
- Derive reasonable assumptions where details are missing.
- Avoid code samples, pseudocode, shell commands, deployment details, CI/CD, or extraneous ADRs.
 - Provide a comprehensive project_structure: include all directories and files
     needed for implementation, testing, configuration, packaging, and operations (e.g. src/,
     tests/, docs/, infra/ or deployment/, scripts/, configs/, tooling, linters). Omit only trivial
     build artifacts.
 - Provide an exhaustive components list that decomposes the system into cohesive, loosely
     coupled units.
 - For EACH component you MUST include a "paths" array listing one or more relative paths
     drawn from project_structure.path values that the component primarily owns / implements.
     Every component must map to at least one path and only to paths that appear in
     project_structure. This mapping enables the planner to group implementation steps.
- In the packages list include notable frameworks, libraries or tools (runtime & dev) beyond the
    primary language, dependency manager and test framework. Use simple
    lowercase package names (e.g. fastapi, sqlalchemy, redis, pytest-cov) without versions.
- For each component supply a comprehensive list covering core and
    edge interactions. Use the format: "As a <role> I want <goal> so that <reason>". Do not invent
    obviously duplicate stories across components—place each story with the component that owns
    fulfilling it.
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
"""


system_designer_agent = Agent(
    name="SYSTEM_DESIGNER_AGENT",
    description="Creates an architectural/system design for a software assignment.",
    instruction=SYSTEM_DESIGN_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],  # No execution tools needed for pure design
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(system_designer_agent)
after_model_call_callback = make_log_after_model_call(system_designer_agent)
system_designer_agent_tool = make_run_agent_as_tool_function(
    agent=system_designer_agent,
    tool_description="""
    Produce a clear, actionable software architecture for the given assignment.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
