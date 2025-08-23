"""Test planner agent implementation."""

from __future__ import annotations

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name
from tools.virtual_computer import (
    append_to_file,
    copy_path,
    make_dirs,
    move_path,
    path_exists,
    read_file_directory,
    remove_path,
    run_bash_cmd,
    write_file,
    write_files,
)

logger = logging.getLogger(__name__)

model = get_model_by_name("coder_architect")

TEST_PLANNER_SYSTEM_PROMPT = (
    "You are TestPlannerAgent. Given the step instructions (assignment) and the coder "
    "output summary, produce a STRICT JSON test plan emphasizing fast, isolated unit "
    "(or small integration) tests. If tests already exist, propose only the minimal "
    "additional coverage needed. Detect (from filenames, existing commands, or paths) "
    "the project's primary language and testing conventions; otherwise stay generic. "
    "Prefer the existing test framework already used. If none is apparent, recommend "
    "a widely adopted lightweight framework (omit install steps unless essential). "
    "Include static analysis / type / lint / format commands ONLY if such tools are "
    "already present or clearly standard. NEVER start long-running services, external "
    "daemons, browsers, or network-heavy processes.\n\n"
    "Return ONLY JSON with this exact schema (no markdown):\n"
    "{\n"
    '  "summary": str,\n'
    '  "test_files": [ { "path": str, "purpose": str } ],\n'
    '  "commands": [ { "run": str, "timeout_sec": int } ],\n'
    '  "rationale": str | null\n'
    "}\n\n"
    "Rules:\n"
    "- Use short relative paths. If a conventional test directory exists (e.g., tests/, "
    "spec/, src/test/), use it; otherwise use tests/.\n"
    "- Always include at least one test file specification.\n"
    "- Command order: optional dependency/setup, tests, then static/type/lint/format.\n"
    "- Use timeouts <=180s per command.\n"
    "- If coder output indicates failure or bugs, add tests that expose those issues.\n"
    "- Keep commands minimal and deterministic (avoid full rebuilds if incremental ok).\n"
    "- Do not invent tools; only use detectable or widely standard defaults.\n"
    """Language-specific tooling guidelines:
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
                        - Include only base deps."""
)

test_planner_agent = Agent(
    name="TEST_PLANNER_AGENT",
    description="Plans unit test files and verification commands.",
    instruction=TEST_PLANNER_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        run_bash_cmd,
        write_file,
        read_file_directory,
        make_dirs,
        remove_path,
        move_path,
        copy_path,
        append_to_file,
        write_files,
        path_exists,
    ],
    think=model.think,
)

_before = make_log_before_model_call(test_planner_agent)
_after = make_log_after_model_call(test_planner_agent)

test_planner_agent_tool = make_run_agent_as_tool_function(
    agent=test_planner_agent,
    tool_description="Plan tests (files + commands) for the coder step; return strict JSON.",
    before_model_callbacks=[_before],
    after_model_callbacks=[_after],
)

__all__ = [
    "test_planner_agent",
    "test_planner_agent_tool",
]
