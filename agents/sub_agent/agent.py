"""Sub-agent that COMPUTRON can spawn to delegate complex work.

The sub-agent has access to the virtual computer, filesystem, and custom tools.
It runs in its own agent span so tool call events appear correctly attributed in
the UI. File output, audio playback, and memory are handled by COMPUTRON after
the sub-agent returns.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from sdk import (
    default_hooks,
    run_tool_call_loop,
)
from agents.browser import browser_agent_tool
from sdk.context import ContextManager, ConversationHistory, SummarizeStrategy
from sdk.events import agent_span, get_model_options
from agents.types import Agent
from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.skills import apply_skill, lookup_skills
from tools.generation import generate_media
from tools.virtual_computer import (
    apply_text_patch,
    describe_image,
    grep,
    list_dir,
    read_file,
    replace_in_file,
    run_bash_cmd,
    write_file,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = dedent(
    """
    You are a worker sub-agent spawned by COMPUTRON 9000. Complete your task thoroughly.

    Check for existing custom tools before writing new code (lookup_custom_tools or
    run_custom_tool). Prefer write_file over shell redirects. Use grep to find code,
    then read_file(start=N, end=M) for targeted sections — avoid reading entire large
    files. Use apply_text_patch for precise edits and replace_in_file for bulk
    find/replace. Use generate_media
    for images. Use run_browser_agent_as_tool for any web browsing. Use describe_image
    to analyze images from the container.
    Do NOT run "pip install torch".

    In HTML/web content, reference assets by container path
    (e.g. src="/home/computron/workspace/sprite.png"), never base64.

    SKILLS — Before starting, check if a proven workflow exists for your task:
    lookup_skills(query). If found, use apply_skill(name, params) to get a
    step-by-step plan. Follow it but adapt as needed.

    FILE OUTPUT — Do NOT call output_file. Instead, include the full paths of every
    file you created in your return summary so COMPUTRON can deliver them.

    Verify correctness, retry on failure. Return a concise summary with all file paths.
    """
)
_TOOLS = [
    # Reading
    read_file,
    grep,
    list_dir,
    # Writing
    write_file,
    # Editing
    apply_text_patch,
    replace_in_file,
    # Shell
    run_bash_cmd,
    # Media
    generate_media,
    describe_image,
    # Browsing
    browser_agent_tool,
    # Custom tools
    create_custom_tool,
    lookup_custom_tools,
    run_custom_tool,
    # Scratchpad
    save_to_scratchpad,
    recall_from_scratchpad,
    # Skills
    lookup_skills,
    apply_skill,
]


async def run_sub_agent(instructions: str, agent_name: str = "SUB_AGENT") -> str:
    """Spawn a named sub-agent to handle a complex or lengthy task without consuming COMPUTRON's own context.

    The sub-agent has full access to the virtual computer,
    filesystem, and custom tools.

    Args:
        instructions: Detailed task instructions — what to do, which tools to prioritise,
            and what to return. Be specific.
        agent_name: Short uppercase name describing this agent's role, shown in the UI
            (e.g. VIDEO_GENERATOR, DATA_ANALYST, FILE_ORGANISER). Defaults to SUB_AGENT.

    Returns:
        str: Summary of what the sub-agent accomplished.
    """
    model_options = get_model_options()
    effective_max_iterations = 0
    if model_options and model_options.max_iterations is not None:
        effective_max_iterations = model_options.max_iterations
    agent = Agent(
        name=agent_name,
        description="",
        instruction=_SYSTEM_PROMPT,
        tools=_TOOLS,
        model=model_options.model if model_options and model_options.model else "",
        think=model_options.think if model_options and model_options.think is not None else False,
        options=model_options.to_options() if model_options else {},
        max_iterations=effective_max_iterations,
    )
    with agent_span(agent_name):
        history = ConversationHistory([
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": instructions},
        ])
        num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
        ctx_manager = ContextManager(
            history=history,
            context_limit=num_ctx,
            agent_name=agent.name,
            strategies=[SummarizeStrategy()],
        )
        hooks = default_hooks(
            agent,
            max_iterations=effective_max_iterations,
            ctx_manager=ctx_manager,
        )
        result_text = ""
        try:
            async for content, _ in run_tool_call_loop(
                history=history,
                agent=agent,
                hooks=hooks,
            ):
                if content:
                    result_text = content
        except Exception:
            logger.exception("Unexpected error in sub-agent '%s'", agent_name)
            raise
        return result_text.strip()
