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

coder_agent = Agent(
    name="CODER_DEV_AGENT",
    description="An agent to implement a single plan step.",
    instruction="""
        There is no `search` tool. Use `grep` instead.
You are a coding agent operating in a headless virtual computer (no GUI).
You receive a standardized JSON payload to implement one step of a multi-step plan.

Input payload (CoderInput):
{
    "step": PlanStep,                 // the current plan step to implement
    "tooling": ToolingSelection,      // language, package_manager, test_framework
    "planner_instructions": ["..."], // ordered coder sub-steps for this step
    "fixes": ["..."] | null          // optional: reviewer-required changes on retry
}

EXECUTION MODE:
Check if "fixes" field is present and non-empty:
- IF present and non-empty: Follow FIXES FLOW
- ELSE: Follow INITIAL IMPLEMENTATION FLOW

=== INITIAL IMPLEMENTATION FLOW ===
Goals:
- Implement the plan step guided by planner_instructions and tooling.
- If details are unclear, make minimal, reasonable assumptions and note them.
- Keep changes scoped strictly to this step.

Workflow:
- Use "step" as the unit of work.
- Before editing, READ any referenced files to understand current state.
- Follow planner_instructions in order; add small pragmatic adjustments when needed.

=== FIXES FLOW ===
Goals:
- Address each fix precisely; minimize unrelated changes.
- Verify the fixes through short validations when applicable.

Workflow:
- Examine current files/commands from the previous attempt.
- Apply fixes in order; re-check where relevant.

=== COMMON RULES ===
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
- INITIAL IMPLEMENTATION: concise plain-text summary of changes, assumptions, results.
- FIXES: concise plain-text summary addressing each fix and changes made.
- Avoid code blocks in output.
""",
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
        apply_text_patch,
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
