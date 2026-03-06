"""General-purpose coding agent for file operations and code changes.

Provides COMPUTRON with a lightweight coding tool that has full access to
the virtual computer filesystem via structured tools (read_file, grep,
replace_in_file, etc.) rather than relying on bash for everything.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
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

NAME = "CODING_AGENT"
DESCRIPTION = (
    "General-purpose coding agent — reads, writes, and modifies files, "
    "searches code, and runs commands in the virtual computer."
)
SYSTEM_PROMPT = dedent(
    """\
    You are CODING_AGENT, a general-purpose coding agent inside COMPUTRON_9000.

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
]

coding_agent_tool = make_run_agent_as_tool_function(
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
    "coding_agent_tool",
]
