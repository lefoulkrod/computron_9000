"""Coder development agent implementation."""

from textwrap import dedent

from agents.ollama.coder.context_models import generate_coder_input_schema_summary
from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.virtual_computer import (
    append_to_file,
    apply_text_patch,
    copy_path,
    describe_image,
    exists,
    grep,
    insert_text,
    list_dir,
    make_dirs,
    move_path,
    prepend_to_file,
    read_file,
    remove_path,
    replace_in_file,
    run_bash_cmd,
    write_file,
)

_CODER_INPUT_SCHEMA = generate_coder_input_schema_summary()

NAME = "CODER_DEV_AGENT"
DESCRIPTION = "An agent to implement a single plan step."
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
- Prefer grep to locate relevant code, then read_file(start=N, end=M) for targeted
  sections. Avoid reading entire large files when only a portion is needed.

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
TOOLS = [
    run_bash_cmd,
    make_dirs,
    remove_path,
    move_path,
    copy_path,
    append_to_file,
    write_file,
    exists,
    read_file,
    grep,
    list_dir,
    replace_in_file,
    insert_text,
    apply_text_patch,
    prepend_to_file,
    describe_image,
    save_to_scratchpad,
    recall_from_scratchpad,
]

coder_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "coder_agent_tool",
]
