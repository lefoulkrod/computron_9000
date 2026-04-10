"""Coder skill — file I/O, code editing, bash execution."""

from textwrap import dedent

from sdk.skills import Skill
from tools.virtual_computer import (
    apply_text_patch,
    grep,
    list_dir,
    read_file,
    replace_in_file,
    run_bash_cmd,
    write_file,
)

_SKILL = Skill(
    name="coder",
    description="File I/O, code editing, bash execution, codebase search",
    prompt=dedent("""\
        Full access to the virtual computer filesystem and shell.

        STARTING A TASK — first check if your instructions reference existing files
        or folders. If they do, work in that existing folder. Otherwise, create a
        new folder under /home/computron/ with a descriptive name.

        SEARCHING — use grep(pattern, path="dir/") to scope searches to a
        directory or single file. Omit path to search the entire workspace.

        READING FILES — always read a file before editing it. read_file returns
        content with embedded line numbers (cat -n style). Use grep to locate
        relevant code, then read_file(start=N, end=M) for targeted sections.

        EDITING FILES — use apply_text_patch(path, old_text, new_text) for precise
        edits: old_text must match exactly one location in the file. Copy old_text
        from the file content exactly — do not include line number prefixes. Use
        replace_in_file for bulk find/replace across a file. Use write_file only
        for new files or complete rewrites.

        COMMANDS — use run_bash_cmd for running tests, installs, and short-lived
        commands. run_bash_cmd has a timeout (default 600s) — if a process runs
        longer, the call will hang until it times out.

        LONG-RUNNING PROCESSES — games, GUIs, servers, watchers, and anything
        that runs indefinitely MUST be backgrounded with & and stdout/stderr
        redirected:
            run_bash_cmd("cd /home/computron/game && python game.py > /dev/null 2>&1 &")
        Then check output with separate commands (log files, curl, etc.).
        NEVER run a long-lived process in the foreground — it will block until
        timeout.

        SERVERS — the container uses host networking, so any port you listen on
        is directly accessible at localhost:<port>. Use ports 8000-8010 to avoid
        conflicts (8080 is taken by the app server).

        INSTALLING PACKAGES — use run_bash_cmd("sudo apt-get install -y ...")
        for system packages, "pip install ..." for Python, "npm install ..."
        for Node.

        GIT & GITHUB — git and the GitHub CLI (gh) are available. Use gh for
        creating PRs, issues, checking CI status, browsing repos, etc.

        PRE-INSTALLED: torch, torchaudio, torchvision (with CUDA), flask,
        flask-socketio, numpy, pandas, scipy, scikit-learn, matplotlib, pillow,
        git, gh, and many more are already installed. Do NOT reinstall these.
    """),
    tools=[
        read_file,
        grep,
        list_dir,
        write_file,
        apply_text_patch,
        replace_in_file,
        run_bash_cmd,
    ],
)
