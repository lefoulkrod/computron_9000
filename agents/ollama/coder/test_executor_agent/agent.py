"""Test executor agent implementation."""

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

TEST_EXECUTOR_SYSTEM_PROMPT = (
    "You are TestExecutorAgent. Run ONLY the provided short-lived verification commands "
    "sequentially. Never infer new commands or run servers. Return STRICT JSON matching:\n"
    "{\n"
    '  "success": bool,\n'
    '  "passed": int,\n'
    '  "failed": int,\n'
    '  "outcomes": [ { "command": str, "exit_code": int, "ok": bool, '
    '"stdout_preview": str | null, "stderr_preview": str | null } ]\n'
    "}\n"
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

test_executor_agent = Agent(
    name="TEST_EXECUTOR_AGENT",
    description="Executes test/verification commands; returns structured JSON report.",
    instruction=TEST_EXECUTOR_SYSTEM_PROMPT,
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

_before = make_log_before_model_call(test_executor_agent)
_after = make_log_after_model_call(test_executor_agent)

test_executor_agent_tool = make_run_agent_as_tool_function(
    agent=test_executor_agent,
    tool_description=(
        "Execute provided commands (tests, lint, type checks) and return strict JSON report."
    ),
    before_model_callbacks=[_before],
    after_model_callbacks=[_after],
)

__all__ = [
    "test_executor_agent",
    "test_executor_agent_tool",
]
