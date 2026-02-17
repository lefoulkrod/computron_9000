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
    ask_about_screenshot,
    click,
    drag,
    execute_javascript,
    fill_field,
    go_back,
    open_url,
    press_keys,
    scroll_page,
    select_option,
    view_page,
)

logger = logging.getLogger(__name__)


# Use default model unless a specialized one is needed; mirrors other agents
model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    Browser automation agent using Playwright. Browser persists state (cookies/storage/tabs)—reuse pages.

    CORE TOOLS:
    Navigation: open_url(url), scroll_page(dir, amt), go_back()
    Reading: view_page(scope?) — see what's on screen with [role] name markers
    Actions: click(selector), fill_field(selector, value), press_keys(keys), select_option(selector, value)
    Vision⚠️ SLOW: ask_about_screenshot()

    IMPORTANT — open_url vs view_page:
    - open_url(url) NAVIGATES to a new URL — use only when you need a different page
    - view_page() reads the CURRENT page without navigating — use to check what's on screen
    After any action (click, fill, scroll), use view_page() to see the updated page.

    VIEW_PAGE — YOUR PRIMARY READING TOOL:
    view_page() returns interleaved content and interactive elements for the current viewport:
        [link] Amazon Prime
        [searchbox] Search Amazon
        [h1] 1-16 of over 50,000 results for "wireless headphones"
        [h2] Results
        [link] Sony WH-1000XM5 Wireless Headphones
        $348.00
        [button] Add to Cart

    SELECTORS — Copy from view_page output, use as role:name:
        click("button:Add to Cart")
        fill_field("searchbox:Search Amazon", "laptop")
        click("link:Sony WH-1000XM5 Wireless Headphones")

    Scoping: view_page(scope="Results") narrows to a page section (matches headings/landmarks).
    After scroll: view_page() shows new viewport content.
    After click/fill: the returned page_view shows the updated page automatically.

    EFFICIENT PATTERNS:
    - ALWAYS prefer site search/filters over scrolling through results
    - view_page() shows what's visible — scroll + view_page to see more
    - Use scope to focus on specific sections without noise
    - Dismiss overlays early (click close/dismiss buttons)

    WORKFLOW:
    1. open_url(url) → view_page() to see the page
    2. Use site search if available: fill_field("searchbox:...", query) → press_keys(["Enter"])
    3. view_page() or view_page(scope="Results") to read results
    4. Click elements using role:name from view_page: click("link:Product Name...")
    5. scroll_page("down") → view_page() to see more content
    6. If stuck/ambiguous: ASK USER for clarification

    WHEN STUCK:
    - Can't find element: scroll + view_page, or use view_page(scope="...") to focus
    - Ambiguous instructions: Ask user to clarify
    - Multiple similar elements: use index suffix click("button:Add to Cart[0]")
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
        view_page,
        click,
        fill_field,
        press_keys,
        select_option,
        scroll_page,
        go_back,
        drag,
        ask_about_screenshot,
        execute_javascript,
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
