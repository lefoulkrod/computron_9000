"""Simple browser agent definition constants.

This agent is intentionally minimal: it can open a URL, summarize textual content, and
optionally visually inspect pages via a vision model.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from config import load_config
from sdk import make_run_agent_as_tool_function
from tools.browser import (
    browse_page,
    click,
    drag,
    execute_javascript,
    fill_field,
    go_back,
    inspect_page,
    open_url,
    press_and_hold,
    press_keys,
    read_page,
    save_page_content,
    scroll_page,
    select_option,
)
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

NAME = "BROWSER_AGENT"
DESCRIPTION = (
    "Browse and interact with web pages: navigate, read content, click, fill forms, scroll, and execute JavaScript."
)

_VISION_SECTION = """\

    VISION vs REF-BASED TOOLS:
    browse_page() gives you ref numbers for every interactive element:
        [3] [link] Datasets       → click("3")
        [5] [button] Submit       → click("5")
        [8] [menuitem] Search     → click("8")
    Prefer ref-based tools (click, fill_field, drag, select_option) when
    elements have clear refs. Use vision tools (browser_visual_action,
    inspect_page) when:
    - Elements have no ref (canvas, images, CAPTCHAs, custom widgets)
    - You need to interact based on visual appearance (colors, shapes, layout)
    - A ref-based action failed
    - You need to answer a question about what the page looks like
"""

_WHEN_STUCK_WITH_VISION = """\
    - Ref failed → try browser_visual_action("describe what to do")
"""

_WHEN_STUCK_WITHOUT_VISION = """\
    - Ref failed → scroll + browse_page() to get fresh refs
"""


def _build_prompt() -> str:
    """Build browser agent prompt, including vision sections only when enabled."""
    grounding = load_config().features.visual_grounding

    vision_block = _VISION_SECTION if grounding else ""
    stuck_line = _WHEN_STUCK_WITH_VISION if grounding else _WHEN_STUCK_WITHOUT_VISION

    return dedent("""\
    Browser automation agent.  Browser persists state (cookies/tabs) between calls.

    SELECTORS: Use ref numbers from browse_page() output.
    Each interactive element has a ref number: [7] [button] Add to Cart
    Pass the ref number to tools:
        click("7")
        fill_field("9", "query")
        select_option("10", "Option Text")

    FORMS: Match the tool to the element role shown by browse_page():
        [textbox] / [searchbox] → fill_field("7", "value")
        [combobox] (<select>)   → select_option("7", "Option Text")
        [combobox] (autocomplete) → fill_field("7", "text"),
                                    then browse_page() and click the matching option
        [checkbox]              → click("7")  (toggles on/off)
        [radio]                 → click("7")
        [button]                → click("7")
    SLIDERS: [slider] elements are adjusted with drag(). browse_page() shows
    the current value after dragging (e.g. [7] [slider] Volume = 8).

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

    DEV SERVERS: The coding agent can start servers inside the container
    (e.g. Flask, FastAPI, Node). These are accessible at localhost:<port>.
    Common ports: 8000-8010 (8080 is the app server). Example:
        open_url("http://localhost:8000")

    DOWNLOADING FILES:
    Click any file link to download it — the browser saves it automatically:
        click("7")  → saved to /home/computron/data.csv
    The tool response will tell you the saved path. Then use run_bash_cmd
    to process the file (grep, head, cat, python, etc.).

    RULES:
    - Prefer the browser for web fetching. Use curl/wget via run_bash_cmd
      ONLY for direct file downloads (PDFs, CSVs, ZIPs) when you have the URL.
    - When you save/download a file, mention the path in your response.
    {vision_block}
    SLIDERS: Drag sliders to the far end of the track unless a specific value is requested.

    SCRATCHPAD: Use save_to_scratchpad to note key findings as you go —
    prices, URLs, names, dates, error messages, or any data you may need
    later. Scratchpad entries persist for the entire conversation and are
    shared across all agents. Earlier tool results may be cleared from
    context to save space, so the scratchpad is the reliable way to keep
    important data available.

    WHEN STUCK:
    - Ref not found → page may have changed, call browse_page() for fresh refs
    - Can't find element → scroll + browse_page, or browse_page(scope="...")
{stuck_line}\
    - Page too complex → save_page_content("page.md") + run_bash_cmd("grep ...")
    - Ambiguous → ask user for clarification

    """).format(vision_block=vision_block, stuck_line=stuck_line)


def _build_tools() -> list:
    """Build browser tools list, including vision tools only when enabled."""
    tools = [
        open_url,
        browse_page,
        read_page,
        click,
        press_and_hold,
        fill_field,
        press_keys,
        select_option,
        scroll_page,
        go_back,
        drag,
        inspect_page,
        execute_javascript,
        save_page_content,
        run_bash_cmd,
    ]
    if load_config().features.visual_grounding:
        from tools.browser import browser_visual_action
        tools.append(browser_visual_action)
    return tools


SYSTEM_PROMPT = _build_prompt()
TOOLS = _build_tools()

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
