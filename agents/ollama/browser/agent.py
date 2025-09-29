"""Simple browser agent implementation with URL summary and screenshot Q&A tools.

This agent is intentionally minimal: it can open a URL, summarize textual content, and
ask the vision model questions about a captured screenshot. It mirrors the structure
of the Coder agent for consistency across agents.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from textwrap import dedent

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.browser import current_page, extract_text, fill_field, open_url
from tools.browser.ask_about_screenshot import ask_about_screenshot
from tools.browser.interactions import click

logger = logging.getLogger(__name__)


# Use default model unless a specialized one is needed; mirrors other agents
model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    You are a lightweight browser agent.

    You have six tools:
    - open_url(url): opens a webpage and returns title, snippet (first ~800 visible characters),
      elements (anchors and forms; up to 20 anchors + all forms), and status code.
    - click(target): clicks an element on the current page. `target` can be the visible text of an
      element or a selector handle (for example `.btn.primary`, `button#submit`, `input[name='q']`). Returns
      an updated page snapshot after the click (including any navigation changes).
    - extract_text(target, limit=1000): extract visible text from elements. Tries exact visible
      text first, then treats `target` as a selector handle, finally a substring text search. Returns
      a list of {selector, text} objects (selector is a best-effort selector handle) truncated to `limit`.
    - ask_about_screenshot(prompt, *, mode="full_page", selector=None): captures a screenshot of
      the current page (full page, viewport, or a specific selector handle) and sends it to a vision model
      to answer the prompt.
    - current_page(): returns a snapshot of the currently open page WITHOUT creating a new one.
      Use this to recall state or re-extract elements. If no page is open you must first call
      open_url.
    - fill_field(target, value): types text into an input or textarea located by visible text or
      CSS selector and returns the updated page snapshot. Use this before submitting forms or
      triggering actions that require typed input.

    Guidelines:
    - The browser used by these tools is long-lived and preserves session state between calls
      (cookies, localStorage, open pages/tabs). When attempting to access or summarize a page,
      first prefer `current_page()` to see if a relevant page is already open. If the current
      page is relevant to the user's request, reuse it rather than calling `open_url` which may
      create a new page or duplicate navigation. Only call `open_url` when no suitable open page
      exists or when the user explicitly provided a different URL to navigate to.
    - Call open_url exactly with the provided URL when the user requests to open or summarize a
      page.
    - After opening a page, use `click` to follow links or activate elements. When choosing a
      target, prefer the `selector` field provided in the page snapshot's `elements` list as the
      primary locator. Do NOT rely on or assume any internal browser APIs  you only have access
      to the tools listed above (open_url, click, extract_text, ask_about_screenshot, current_page,
      fill_field). Call these tools with the element's `selector` handle when available.
    - If the `selector` handle does not work, you may instead provide the element's visible text to the
      tool as a fallback (for example, `click("Sign in")`), but always attempt the `selector`
      first.
    - Use extract_text to pull structured text from specific regions or elements instead of taking
      a screenshot when plain text suffices.
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
        "An agent that opens a URL, summarizes the page, and can ask visual questions about a captured screenshot."
    ),
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[open_url, click, extract_text, ask_about_screenshot, current_page, fill_field],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(browser_agent)
after_model_call_callback = make_log_after_model_call(browser_agent)

browser_agent_tool: Callable[[str], Awaitable[str]] = make_run_agent_as_tool_function(
    agent=browser_agent,
    tool_description="An agent that can use a browser to interact with web pages.",
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "browser_agent",
    "browser_agent_tool",
]
