"""General-purpose computer agent with full virtual container access.

Provides COMPUTRON with an agent that has full access to the virtual
computer filesystem via structured tools (read_file, grep,
replace_in_file, etc.) and bash for everything from code to asset
generation.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.skills import apply_skill, lookup_skills
from tools.virtual_computer import (
    append_to_file,
    apply_text_patch,
    copy_path,
    exists,
    grep,
    list_dir,
    move_path,
    read_file,
    remove_path,
    replace_in_file,
    run_bash_cmd,
    tail,
    write_file,
)

logger = logging.getLogger(__name__)

NAME = "COMPUTER_AGENT"
DESCRIPTION = (
    "Computer agent — full access to the virtual computer. Writes code, "
    "generates assets (audio, images, SVGs), runs commands, edits files, "
    "and searches codebases. Use for any work that involves creating or "
    "modifying files."
)
SYSTEM_PROMPT = dedent(
    """\
    You are COMPUTER_AGENT, a general-purpose agent inside COMPUTRON_9000
    with full access to the virtual computer.

    STARTING A TASK — first check if your instructions reference existing files
    or folders. If they do, you are resuming — work in that existing folder.
    Otherwise, create a new folder under /home/computron/ with a descriptive
    name (e.g. /home/computron/todo-app/).

    PLANNING — for multi-step or multi-file tasks, before writing any code:
    1. Write a plan.md in the project folder with numbered steps.
    2. Execute one step at a time.
    3. After each step, re-read plan.md and mark the completed step done.
    Skip the plan for single-file edits or simple changes.
    If resuming and plan.md already exists, read it and continue from where
    it left off.

    SEARCHING — use grep(pattern, path="dir/") to scope searches to a
    directory or single file. Omit path to search the entire workspace.

    READING FILES — always read a file before editing it. read_file returns
    content with embedded line numbers (cat -n style) so you can reference
    specific lines. Use grep to locate relevant code, then
    read_file(start=N, end=M) for targeted sections. Use tail to check the
    end of files (logs, output). Files over 2000 lines are automatically
    truncated; use start/end to read specific sections of large files.

    EDITING FILES — use apply_text_patch(path, old_text, new_text) for precise
    edits: old_text must match exactly one location in the file. Copy old_text
    from the file content exactly — do not include line number prefixes. Use
    replace_in_file for bulk find/replace across a file. Use write_file only
    for new files or complete rewrites. Prefer editing existing files over
    creating new ones.

    COMMANDS — use run_bash_cmd for running tests, installs, and short-lived
    commands. Do NOT start servers or long-running processes.

    Do NOT run "pip install torch" — it overwrites the CUDA build.

    SKILLS — Before starting, check if a proven workflow exists for your task:
    lookup_skills(query). If found, use apply_skill(name, params) to get a
    step-by-step plan. Follow it but adapt as needed.

    Return a concise summary of changes with all file paths when done.
    """
)
TOOLS = [
    # Reading
    read_file,
    tail,
    grep,
    list_dir,
    exists,
    # Writing
    write_file,
    append_to_file,
    # Editing
    apply_text_patch,
    replace_in_file,
    # File management
    remove_path,
    move_path,
    copy_path,
    # Shell
    run_bash_cmd,
    # Scratchpad
    save_to_scratchpad,
    recall_from_scratchpad,
    # Skills
    lookup_skills,
    apply_skill,
]

computer_agent_tool = make_run_agent_as_tool_function(
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
    "computer_agent_tool",
]
