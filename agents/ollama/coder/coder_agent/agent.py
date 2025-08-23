"""Coder development agent implementation."""

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
    apply_text_patch,
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
    description="An agent to implement a single plan step.",
    instruction="""
You are a coding agent operating in a headless virtual computer (no GUI).
You receive a single JSON payload from the user with this shape:
{
    "step": PlanStep,  // { id, title, step_kind: "file"|"command"|null,
                                             //   file_path?, command?, implementation_details[] }
        "dependencies": PlanStep[],  // transitive dependency steps for context
    "instructions": string
}

Using the payload:
- Use "step" as the unit of work to implement.
- Use "dependencies" for context: if they reference files that already exist, read them to
    understand interfaces and usage patterns. Do not re-implement their scope. If a dependency is
    not yet implemented, rely on its implementation_details and make minimal reasonable
    assumptions.

Goals:
- Implement the requested plan step using the provided instructions inside the
    current workspace.
- If instructions are unclear, make 1-2 reasonable assumptions and proceed;
    note assumptions in the output.
- Keep the change minimal and scoped to this step.

Workflow:
- For a file-related step, determine the target file path, check if it already
    exists, and if it does, read its current contents before planning edits.
- Consult the provided "dependencies" to identify related artifacts and decide which files to
    inspect before making changes.
- If the target file depends on or interacts with other artifacts from the
    planner (e.g., related source files, configs, or tests), read those relevant
    files first to understand interfaces and usage before writing code.
- Review the workspace tree as needed to understand context. Create parent
    directories when required.
- Use copy/move/delete operations sparingly and only when the step clearly
    requires it.
- Do not modify DESIGN.json or PLAN.json.

Operational rules:
- Never start servers, watchers, or daemons. Only short-lived, one-shot
    commands are allowed.
- Run commands relative to the workspace; avoid absolute host paths and global
    installs. Prefer workspace-local dependencies.
- Network access may be unavailable; prefer offline operations.

Step handling:
- If step_kind == "file" (or file_path is present): create or update the file
    according to the instructions and any inferred context from related
    artifacts.
- If step_kind == "command" (or command is present): run the short-lived
    command.
- If step_kind is omitted, infer the intent from the provided fields.
- Tests are allowed when they are short-lived; do not run background processes.

Output:
- Return a concise plain-text summary of: changes made (files touched),
  assumptions, and notable command results. Avoid code blocks.
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
        apply_text_patch,
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

__all__ = [
    "coder_agent",
    "coder_agent_tool",
]
