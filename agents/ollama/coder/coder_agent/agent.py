"""Coder development agent implementation."""

import logging
from textwrap import dedent

from agents.ollama.coder.context_models import generate_coder_input_schema_summary
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
    exists,
    grep,
    head,
    insert_text,
    list_dir,
    make_dirs,
    move_path,
    read_file,
    remove_path,
    replace_in_file,
    run_bash_cmd,
    tail,
    write_file,
)

logger = logging.getLogger(__name__)

model = get_model_by_name("coder_developer")

_CODER_INPUT_SCHEMA = generate_coder_input_schema_summary()

SYSTEM_PROMPT = dedent(
    f"""
        There is no `search` tool. Use `grep` instead.
You are a coding agent operating in a headless virtual computer (no GUI).
You receive a standardized JSON payload to implement one step of a multi-step plan.

Input JSON payload (CoderInput)
{_CODER_INPUT_SCHEMA}

Execution guidance:
- Use the provided "instructions" list in order. If they are reviewer fixes, address them precisely.
- Keep changes scoped strictly to this step and the instructions.
- If details are unclear, make minimal, reasonable assumptions and note them.

Common rules:
- Review the workspace tree as needed; avoid package folders (node_modules, .venv).
- Do not modify DESIGN.json or PLAN.json.
- Never start servers/watchers; use only short-lived commands.
- Never read the full contents of lock files or package directories.

Step handling:
- If step_kind == "file" (or file_path present): create/update the file.
- If step_kind == "command" (or command present): run the short-lived command.
- If step_kind omitted: infer intent from fields.
- Tests are allowed when short-lived; no background processes.

Output:
- Concise plain-text summary of changes, assumptions, and results.
- Avoid code blocks in output.
"""
)

coder_agent = Agent(
    name="CODER_DEV_AGENT",
    description="An agent to implement a single plan step.",
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        run_bash_cmd,
        make_dirs,
        remove_path,
        move_path,
        copy_path,
        append_to_file,
        write_file,
        exists,
        read_file,
        head,
        tail,
        grep,
        list_dir,
        replace_in_file,
        insert_text,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(coder_agent)
after_model_call_callback = make_log_after_model_call(coder_agent)
coder_agent_tool = make_run_agent_as_tool_function(
    agent=coder_agent,
    tool_description="""
    Implement a single plan step using the provided standardized context (CoderInput),
    performing code edits and short-lived commands as needed. Returns a plain-text summary.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "coder_agent",
    "coder_agent_tool",
]
