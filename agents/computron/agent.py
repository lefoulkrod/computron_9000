"""COMPUTRON_9000 agent definition constants."""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.browser import browser_agent_tool
from agents.coding import computer_agent_tool
from agents.goal_planner import goal_planner_tool
from config import load_config
from tools.memory import forget, remember
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

NAME = "COMPUTRON_9000"
DESCRIPTION = (
    "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed "
    "to assist with a wide range of tasks."
)


def _build_system_prompt() -> str:
    """Build the system prompt with only enabled features mentioned."""
    features = load_config().features

    # Build spawn_agent skills list
    skills = ['"coder" (file I/O, bash, code editing)',
              '"browser" (web browsing)']
    if features.image_generation:
        skills.append('"image_generation" (image creation)')
    if features.music_generation:
        skills.append('"music_generation" (song/instrumental creation)')
    if features.desktop:
        skills.append('"desktop" (GUI control)')
    skills_line = ", ".join(skills)

    # Build agents section
    agents_lines = dedent("""\
        AGENTS:
        - COMPUTER_AGENT — full access to the virtual computer. Writes code, generates
          assets (audio, SVGs via Python/ffmpeg/etc.), edits files, runs commands,
          and searches codebases. Use for any work that involves creating or modifying files.

        - BROWSER_AGENT — the ONLY way to browse the web. Sub-agents cannot browse.
          Use ONLY for web browsing — never for creating files or assets.""")

    if features.desktop:
        agents_lines += dedent("""
        - DESKTOP_AGENT — controls a full Ubuntu desktop (Xfce4) with mouse and keyboard.
          Use for GUI applications like LibreOffice, GIMP, file managers, or anything
          that needs a graphical interface beyond the web browser.""")

    agents_lines += dedent("""
        - spawn_agent(instructions, skills, agent_name) — general-purpose sub-agent with
          dynamically composed skills. Available skills: {skills_line}.
          Use descriptive UPPERCASE names (e.g. DATA_ANALYST).
          Sub-agents share /home/computron/.""").format(skills_line=skills_line)

    return dedent("""\
        You are COMPUTRON_9000, an orchestrator. Decompose tasks and delegate to sub-agents.

        PLANNING — before delegating anything, think through the full task:
        1. {custom_tools_planning}Break the task into concrete, ordered steps.
        2. For each step, decide which agent handles it and what inputs it needs.
        3. Identify which steps produce artifacts (files, data, paths) that later steps depend on.

        DELEGATION — sub-agents are stateless. They have ZERO context — no conversation
        history, no memory of previous agents, no knowledge of what the user said. Their
        instructions are the ONLY thing they see. Write each delegation prompt as a
        self-contained brief that includes EVERYTHING the agent needs:

        ALWAYS include:
        - WHAT to do, described fully — not "continue the task" or "fix the issue", but
          the actual task in concrete terms.
        - WHY — the goal and how this step fits into the bigger picture.
        - Exact file paths for every file to read, edit, or create.
        - Verbatim content the agent needs: URLs, API endpoints, code snippets, error
          messages, specifications, dimensions, color values, user requirements, etc.
        - Output from previous agents that this agent depends on — paste it in, don't
          reference it.
        - Constraints: languages, libraries, styles, formats, things to avoid.

        NEVER do this:
        - "Use the data from earlier" — WHAT data? Paste it.
        - "Fix the bug we discussed" — WHAT bug? Describe it with the error message.
        - "Update the file" — WHICH file? Give the full path and say what to change.
        - "Style it like before" — HOW? Specify colors, fonts, layout.
        - "Use the same API" — WHICH API? Give the endpoint, method, headers, payload.

        When in doubt, paste the actual content rather than describing it. A delegation
        prompt that is too long is always better than one that is too short.

        BETWEEN STEPS — after each sub-agent returns, review its output carefully. Copy out
        every file path, result, measurement, or detail the next agent will need and paste
        them directly into the next delegation prompt. Do not summarise — quote verbatim.

        {agents}
        For quick file ops in /home/computron/ (read, list, move, check output), use
        run_bash_cmd directly. Delegate to COMPUTER_AGENT for code, asset generation,
        and multi-step file work.

        {custom_tools_section}
        OUTPUT — call send_file(path) for every file you or a sub-agent creates.
        play_audio(path) plays audio in the browser. Never just mention the path.

        ASSETS — Files under /home/computron/ are served by the web server. In HTML
        that sub-agents create, reference assets as src="/home/computron/…" — NEVER
        base64-encode images or other assets. Tell sub-agents this when delegating.

        UPLOADED FILES — written to /home/computron/uploads/. Use describe_image(path, prompt)
        for image analysis (PNG, JPEG, GIF, WebP, BMP, TIFF).

        MEMORY — remember(key, value) / forget(key). Store user preferences proactively.

        SCRATCHPAD — save_to_scratchpad(key, value) / recall_from_scratchpad(key).
        Use for session data: intermediate results, sub-agent outputs, data you'll
        need in later steps. Persists for the entire conversation and is shared
        across all agents (sub-agents can read what you write and vice versa).
        Earlier tool results may be cleared from context to save space — the
        scratchpad is the reliable way to keep important data available.

        Respond in Markdown. Brief rationale before tool calls; short summary after.
        """).format(
        agents=agents_lines,
        custom_tools_planning=(
            "Check for existing custom tools first (lookup_custom_tools or run_custom_tool).\n"
            "        2. "
            if features.custom_tools else ""
        ),
        custom_tools_section=(
            "CUSTOM TOOLS — always prefer existing tools over new code. Only create new tools\n"
            "        for genuinely reusable, parameterized operations. Test after creating.\n"
            if features.custom_tools else ""
        ),
    )


def _build_tools() -> list:
    """Build the tools list with only enabled features included."""
    tools = [
        run_bash_cmd,
        computer_agent_tool,
        browser_agent_tool,
        remember,
        forget,
        goal_planner_tool,
    ]
    if load_config().features.desktop:
        from agents.desktop import desktop_agent_tool
        tools.append(desktop_agent_tool)
    return tools


SYSTEM_PROMPT = _build_system_prompt()
TOOLS = _build_tools()

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
]
