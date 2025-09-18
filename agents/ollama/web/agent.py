"""Standalone web research agent definition and helper exports."""

from __future__ import annotations

from textwrap import dedent

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.reddit import get_reddit_comments_tree_shallow, search_reddit
from tools.web import get_webpage_substring, get_webpage_summary_sections, search_google

model = get_default_model()

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
    5. Pull top-level Reddit reactions through `get_reddit_comments_tree_shallow` when helpful.
    6. Synthesize the findings into a cohesive answer with citations and source links.

    Guidance:
    - Call tools iteratively; review results before deciding the next step.
    - Prefer multiple independent sources when possible.
    - Always include inline citations that map directly to your tool outputs.
    - Make limitations clear if information cannot be found.
    """
)

web_agent: Agent = Agent(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        get_webpage_summary_sections,
        get_webpage_substring,
        search_google,
        search_reddit,
        get_reddit_comments_tree_shallow,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(web_agent)
after_model_call_callback = make_log_after_model_call(web_agent)

web_agent_tool = make_run_agent_as_tool_function(
    agent=web_agent,
    tool_description=DESCRIPTION,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "after_model_call_callback",
    "before_model_call_callback",
    "web_agent",
    "web_agent_tool",
]
