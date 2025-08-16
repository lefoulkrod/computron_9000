"""The agent for the coder development workflow functionality."""

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

model = get_model_by_name("coder_developer")

coder_agent = Agent(
    name="CODER_DEV_AGENT",
    description="An agent designed to create, analyze, execute, and test code.",
    instruction="""
You are a coding agent operating in a headless virtual computer (no GUI). Never start
servers or watchers. Only run short-lived unit/integration tests and setup commands.
All work happens in a per-run workspace folder.

Rules:
- Run bash commands relative to the current working directory (no absolute home paths).
- Install packages locally in the workspace only; never global installs.
- Use `read_file_directory` to confirm files/dirs before operating on them.
- Keep changes minimal and focused per step; update tests alongside refactors.
- Prefer adding tests first based on the plan; then implement until tests pass.

Always return a brief summary of changes made.
""",
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

before_model_call_callback = make_log_before_model_call(coder_agent)
after_model_call_callback = make_log_after_model_call(coder_agent)
coder_agent_tool = make_run_agent_as_tool_function(
    agent=coder_agent,
    tool_description="""
    The coding agent can perform code generation, analysis, execution, and testing
    based on the instructions provided.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
