"""Simple browser agent implementation with URL summary and screenshot Q&A tools.

This agent is intentionally minimal: it can open a URL, summarize textual content, and
ask the vision model questions about a captured screenshot. It mirrors the structure
of the Coder agent for consistency across agents.
"""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from collections.abc import Callable

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.browser import open_url
from tools.browser.ask_about_screenshot import ask_about_screenshot
from tools.browser.interactions import click

logger = logging.getLogger(__name__)


# Use default model unless a specialized one is needed; mirrors other agents
model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    You are a lightweight browser agent.

    You have three tools:
    - open_url(url): opens a webpage and returns title, snippet (first ~800 visible characters),
      links (up to 20 with text + href), forms, and status code.
    - click(target): clicks an element on the current page. `target` can be the visible text of an
      element or a CSS selector (e.g., `.btn.primary`, `button#submit`, `input[name='q']`). Returns
      an updated page snapshot after the click (including any navigation changes).
    - ask_about_screenshot(prompt, *, mode="full_page", selector=None): captures a screenshot of
      the current page (full page, viewport, or a specific selector) and sends it to a vision model
      to answer the prompt.

    Guidelines:
    - Call open_url exactly with the provided URL when the user requests to open or summarize a
      page.
    - After opening a page, use click when you need to follow a link or activate an element before
      further analysis. Prefer visible text for `target` when possible; fall back to a precise CSS
      selector if needed.
    - Use ask_about_screenshot when you need visual details (e.g., "What does the banner say?"),
      optionally adjusting ``mode`` or ``selector`` to focus on the right region, but only after you
      have opened (and if needed, interacted with) the relevant page.
    - Provide a concise summary based on tool outputs.
    - If the URL is missing or invalid, ask for a proper http/https URL.
    - Do not attempt unrelated tasks; only use the provided tools.
    """
)

browser_agent = Agent(
    name="BROWSER_AGENT",
    description=(
        "An agent that opens a URL, summarizes the page, and can ask visual questions "
        "about a captured screenshot."
    ),
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[open_url, click, ask_about_screenshot],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(browser_agent)
after_model_call_callback = make_log_after_model_call(browser_agent)

browser_agent_tool: Callable[..., Any] = make_run_agent_as_tool_function(
    agent=browser_agent,
    tool_description=("An agent that can perform actions by browsing the web."),
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "browser_agent",
    "browser_agent_tool",
]
