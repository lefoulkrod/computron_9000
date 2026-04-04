"""Browser skill — web browsing, page interaction, form filling."""

from textwrap import dedent

from sdk.skills import Skill
from tools.browser import (
    browse_page,
    click,
    drag,
    execute_javascript,
    fill_field,
    go_back,
    inspect_page,
    open_url,
    perform_visual_action,
    press_and_hold,
    press_keys,
    read_page,
    save_page_content,
    scroll_page,
    select_option,
)
from tools.virtual_computer import run_bash_cmd

_SKILL = Skill(
    name="browser",
    description="Web browsing, page interaction, form filling, screenshots",
    prompt=dedent("""\
        Browser automation. Browser persists state (cookies/tabs) between calls.

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
        container file, just prepend http://localhost:8080 to its path.
        Do NOT start your own HTTP server — it is never needed.

        DOWNLOADING FILES:
        Click any file link to download it — the browser saves it automatically.
        The tool response will tell you the saved path. Then use run_bash_cmd
        to process the file (grep, head, cat, python, etc.).

        VISION vs REF-BASED TOOLS:
        Prefer ref-based tools (click, fill_field, drag, select_option) when
        elements have clear refs. Use vision tools (perform_visual_action,
        inspect_page) when:
        - Elements have no ref (canvas, images, CAPTCHAs, custom widgets)
        - A ref-based action failed
        - You need to answer a question about what the page looks like

        WHEN STUCK:
        - Ref not found → page may have changed, call browse_page() for fresh refs
        - Can't find element → scroll + browse_page, or browse_page(scope="...")
        - Ref failed → try perform_visual_action("describe what to do")
        - Page too complex → save_page_content("page.md") + run_bash_cmd("grep ...")
    """),
    tools=[
        open_url,
        browse_page,
        read_page,
        click,
        press_and_hold,
        perform_visual_action,
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
    ],
)
