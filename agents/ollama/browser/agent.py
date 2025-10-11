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
from tools.browser import (
    click,
    current_page,
    drag,
    extract_text,
    fill_field,
    ground_elements_by_text,
    list_clickable_elements,
    open_url,
    press_keys,
    scroll_page,
)
from tools.browser.vision import ask_about_screenshot

logger = logging.getLogger(__name__)


# Use default model unless a specialized one is needed; mirrors other agents
model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    You are a lightweight browser agent. Work with the persistent Playwright browser to inspect pages,
    follow links, fill forms, press keys, and ask vision questions. The browser keeps cookies, storage,
    and tabs between calls—reuse the current page when it's already on target.

    Available tools
    - open_url(url): navigate the shared page and return a snapshot (title, snippet, elements, status).
    - current_page(): snapshot the existing page without opening a new one.
    - click(selector): activate an element; returns an InteractionResult (`page_changed`, `reason`,
      optional `snapshot`).
    - drag(source, target=None, offset=None): drag and drop via selectors or an offset; returns InteractionResult.
    - fill_field(selector, value): click + type into inputs/textarea; InteractionResult.
    - press_keys(keys): send key presses to the focused element; InteractionResult.
    - scroll_page(direction, amount=None): scroll and return InteractionResult with `extras["scroll"]`.
    - extract_text(selector, limit=1000): collect visible text from elements.
    - list_clickable_elements(after=None, limit=20, contains=None): list anchors/buttons/heuristic clickables.
    - ask_about_screenshot(...), ground_elements_by_text(...): vision tools for image-based questions / grounding.

    InteractionResult notes
    - `page_changed` signals whether the browser detected navigation, DOM/layout change, or relevant input.
    - `snapshot` is present only when the page changed; reuse the prior snapshot when it is `None`.
    - `reason` values: `browser-navigation`, `history-navigation`, `dom-mutation`, `no-change`.
    - Native `<select>` dropdowns do not change until an option is chosen. Opening the menu alone keeps
      `page_changed=false`; selecting an option will flip it. This is expected behavior.

        Usage guidelines
        - Start with `current_page()`; only call `open_url` when no relevant page is loaded or when
            the user asks for a new URL.
        - Prefer selector handles from snapshots for `selector`, `source`, and `target` arguments;
            fall back to exact text only when necessary.
        - After every interaction, rely on `page_changed`/`reason` (and snapshots when provided) to
            confirm the effect before proceeding.
        - Use `fill_field` before submitting forms, `press_keys` for keyboard-driven flows, and
            `scroll_page` to reveal lazy content.
        - Keep tool usage aligned with the user's request and provide concise summaries based on
            tool outputs.
        - Ask for a proper http/https URL if one is missing or malformed.
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
    tools=[
        open_url,
        click,
        drag,
        extract_text,
        list_clickable_elements,
        ask_about_screenshot,
        ground_elements_by_text,
        current_page,
        fill_field,
        press_keys,
        scroll_page,
    ],
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
