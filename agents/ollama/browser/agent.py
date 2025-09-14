"""Simple browser agent implementation using the open_url tool only.

This agent is intentionally minimal: it can open a single URL and return a
compact summary (title, snippet, and links). It mirrors the structure of the
Coder agent for consistency across agents.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.browser.open_url import open_url

logger = logging.getLogger(__name__)


# Use default model unless a specialized one is needed; mirrors other agents
model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    You are a lightweight browser agent.

    You have a single tool: open_url(url) which opens a webpage and returns:
    - title
    - snippet (first ~800 chars of visible body text)
    - links (up to 20 with text + href)

    Guidelines:
        - Call open_url exactly with the provided URL when the user requests to open
            or summarize a page.
    - Return a concise summary based on the tool output.
    - If the URL is missing or invalid, ask for a proper http/https URL.
    - Do not attempt unrelated tasks; you only have open_url.
    """
)

browser_agent = Agent(
    name="BROWSER_AGENT",
    description=(
        "An agent that opens a URL and returns a compact summary "
        "(title, snippet, links) using a headless browser."
    ),
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[open_url],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(browser_agent)
after_model_call_callback = make_log_after_model_call(browser_agent)

browser_agent_tool = make_run_agent_as_tool_function(
    agent=browser_agent,
    tool_description=("Open a URL and return title/snippet/links using a shared headless browser."),
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "browser_agent",
    "browser_agent_tool",
]
