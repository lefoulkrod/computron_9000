"""Agent responsible for producing an actionable implementation plan from a system design."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")


PLANNER_SYSTEM_PROMPT = """
Role: Expert Implementation Planner

Input: The software assignment and the designer's architecture brief.
Output: STRICT JSON only - an ordered array of small, executable steps forming the full
implementation plan. No prose outside JSON. No code samples in fields.

Each step must match this shape:
[
    {
        "id": "step-1",
        "title": "Short action-oriented title",
        "instructions": "Concrete instructions describing exactly what to do (no code).",
        "files": [
            { "path": "relative/path", "purpose": "why this file is added/changed" }
        ],
        "commands": [
            { "run": "tool-or-test-runner ...", "timeout_sec": 120 }
        ],
        "tests": [
            { "path": "tests/test_x.py", "description": "what this test verifies" }
        ],
        "acceptance": [ "Objective verification criteria for this step" ],
        "depends_on": [ "step-0" ],
        "retries": 1,
        "when": null
    }
]

Planning rules:
- Derive all actions from the designer's architecture. Resolve ambiguities with reasonable
    assumptions; call them out via step text if impactful.
- Be exhaustive and implementation-ready: include setup, scaffolding, config, types, minimal docs,
    and tests. Prefer tests-first where practical.
- Keep steps small and dependency-ordered. Use "depends_on" to express prerequisites.
- The environment is headless. Only short-lived commands (no servers/watchers/background daemons).
- Paths must be relative to the workspace. Avoid generating files outside the repo.
- Every step must include at least one verification command in "commands" (e.g., unit tests,
    linters, type checkers, format checks). The verifier will run exactly these commands.
- Prefer idempotent commands. Include timeouts appropriate to the task (60-180 seconds typical).
- If the stack requires dependencies or tools, include steps to add them (and lockfiles) before
    using them.
- Include periodic full quality gates (format, lint, type check, tests) after major milestones.

Coverage expectations:
- Bootstrap: project scaffolding and dependency installation.
- Quality: formatters, linters, type checkers configured and validated.
- Data model and API/CLI contracts: skeletons in place with tests.
- Core features: implemented incrementally with tests.
- Error handling, logging, and basic docs/readme updates.
- Final end-to-end verification and cleanup.
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
    Turn a high-level design into a structured, JSON implementation plan.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
