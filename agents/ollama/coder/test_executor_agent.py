"""Test Executor agent: runs provided verification commands and returns JSON report.

Previously VerifierAgent; now focused solely on executing commands.
"""

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
