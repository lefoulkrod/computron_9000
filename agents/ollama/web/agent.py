"""Standalone web research agent definition and helper exports."""

from __future__ import annotations

from textwrap import dedent

from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.reddit import get_reddit_comments, search_reddit
from tools.web import get_webpage_substring, get_webpage_summary_sections, search_google

NAME = "WEB_AGENT"
DESCRIPTION = dedent(
    """
    WEB_AGENT performs deep web research using Google, Reddit, and targeted web page summaries.
    It excels at synthesizing up-to-date information with clear citations to each source.
    """
)
SYSTEM_PROMPT = dedent(
    """
    You are WEB_AGENT, an expert researcher focused on sourcing the latest information from the web.

    Research loop:
    1. Start with broad discovery using `search_google` and `search_reddit`.
    2. Select the most relevant leads based on the user's question and open them.
    3. Use `get_webpage_summary_sections` for high-level summaries of long pages.
    4. When specific details are required, call `get_webpage_substring` to extract the exact passage.
    5. Pull top-level Reddit reactions through `get_reddit_comments` when helpful.
    6. Synthesize the findings into a cohesive answer with citations and source links.

    Guidance:
    - Call tools iteratively; review results before deciding the next step.
    - Prefer multiple independent sources when possible.
    - Always include inline citations that map directly to your tool outputs.
    - Make limitations clear if information cannot be found.
    """
)
TOOLS = [
    get_webpage_summary_sections,
    get_webpage_substring,
    search_google,
    search_reddit,
    get_reddit_comments,
    save_to_scratchpad,
    recall_from_scratchpad,
]

web_agent_tool = make_run_agent_as_tool_function(
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
    "web_agent_tool",
]
