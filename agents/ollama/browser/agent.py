"""Simple browser agent definition constants.

This agent is intentionally minimal: it can open a URL, summarize textual content, and
ask the vision model questions about a captured screenshot.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.browser import (
    ask_about_screenshot,
    browse_page,
    click,
    click_element,
    drag,
    execute_javascript,
    fill_field,
    go_back,
    open_url,
    press_and_hold,
    press_and_hold_element,
    press_keys,
    read_page,
    save_page_content,
    scroll_page,
    select_option,
)
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

NAME = "BROWSER_AGENT"
DESCRIPTION = "Browse and interact with web pages: navigate, read content, click, fill forms, scroll, and execute JavaScript."
SYSTEM_PROMPT = dedent(
    """
    Browser automation agent.  Browser persists state (cookies/tabs) between calls.

    SELECTORS: Use role:name format from browse_page() output.
        click("button:Add to Cart")
        fill_field("searchbox:Search", "query")
        Multiple matches: click("link:Product[0]")

    FORMS: Match the tool to the element role shown by browse_page():
        [textbox] / [searchbox] → fill_field("textbox:Label", "value")
        [combobox] (dropdowns)  → select_option("combobox:Label", "Option Text")
        [checkbox]              → click("checkbox:Label")  (toggles on/off)
        [radio]                 → click("radio:Option Text")
        [button]                → click("button:Label")

    EFFICIENCY:
    - Stop when you have enough data — do NOT scroll for completeness.
    - Prefer site search/filters over scrolling through results.
    - Dismiss overlays early (click close/dismiss buttons).

    LOCAL FILES: ALL files under /home/computron/ are already served at
    http://localhost:8080/home/computron/... by the app server. To view any
    container file, just prepend http://localhost:8080 to its path:
        /home/computron/workspace/index.html
        → open_url("http://localhost:8080/home/computron/workspace/index.html")
    Do NOT start your own HTTP server (python -m http.server, etc.) — it is
    never needed.

    DOWNLOADING FILES:
    Click any file link to download it — the browser saves it automatically:
        click("link:data.csv")  → saved to /home/computron/data.csv
    The tool response will tell you the saved path. Then use run_bash_cmd
    to process the file (grep, head, cat, python, etc.).

    RULES:
    - Prefer the browser for web fetching. Use curl/wget via run_bash_cmd
      ONLY for direct file downloads (PDFs, CSVs, ZIPs) when you have the URL.
    - When you save/download a file, mention the path in your response.

    VISION TOOLS — STRICT RULES:
    click_element, press_and_hold_element, and ask_about_screenshot use
    vision (screenshot analysis) which is 10x slower and more expensive.
    NEVER use a vision tool unless you have ALREADY tried the selector-based
    equivalent (click, fill_field, etc.) on the SAME page and it FAILED.
    browse_page() gives you exact [role] name selectors — use them directly:
        [link] Datasets       → click("link:Datasets")
        [button] Submit       → click("button:Submit")
        [menuitem] Search     → click("menuitem:Search")
    Vision is ONLY for elements that have no selector (e.g. canvas, images,
    CAPTCHAs) or after a selector-based click has failed twice.

    WHEN STUCK:
    - Can't find element → scroll + browse_page, or browse_page(scope="...")
    - Selector failed twice → THEN use click_element("describe it visually")
    - Page too complex → save_page_content("page.md") + run_bash_cmd("grep ...")
    - Multiple similar elements → use index suffix: click("button:Submit[0]")
    - Ambiguous → ask user for clarification
    """
)
TOOLS = [
    open_url,
    browse_page,
    read_page,
    click,
    click_element,
    press_and_hold,
    press_and_hold_element,
    fill_field,
    press_keys,
    select_option,
    scroll_page,
    go_back,
    drag,
    ask_about_screenshot,
    execute_javascript,
    save_page_content,
    run_bash_cmd,
    save_to_scratchpad,
    recall_from_scratchpad,
]

browser_agent_tool = make_run_agent_as_tool_function(
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
    "browser_agent_tool",
]
