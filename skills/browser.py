"""Browser skill — web browsing, page interaction, form filling."""

from textwrap import dedent

from sdk.skills import Skill
from tools.browser import (
    browse_page,
    browser_visual_action,
    click,
    close_tab,
    drag,
    execute_javascript,
    fill_field,
    go_back,
    goto,
    inspect_page,
    new_tab,
    press_and_hold,
    press_keys,
    read_page,
    save_page_content,
    scroll_page,
    select_option,
)
from tools.web import fetch_url
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
            [link]                  → click("7")  (NOT goto)

        NAVIGATION: goto(url) is for URLs from outside the browser — user
        input, fetch_url output, addresses you were told to visit. To follow a
        link that appears in the current page (search results, article links,
        nav items), always use click(ref) on the [link]'s ref number. Never
        fabricate a URL from the visible link text — the ref already knows the
        real href, and guessed URLs land on unrelated pages.

        TABS: every tab has a stable ID shown in snapshot headers as
        ``tab=N``. Once you've seen an ID it never changes — closing a
        tab does not renumber the rest.
            new_tab(url)         — the only way to open a tab. Use this
                                   for the first URL of a session and
                                   any time you want a fresh page.
            goto(url, tab="3")   — re-point an existing tab to a new
                                   URL. Tab is required. Use this when
                                   you want to reuse a tab rather than
                                   open another one.
            close_tab(tab="3")   — close a tab when you're done with it.
        Page-acting tools (click, scroll_page, read_page, browse_page,
        fill_field, ...) all require ``tab="N"``. Tools error with the
        open-tab listing when ``tab`` is missing or unknown. Concurrent
        goto on the same tab errors — use new_tab(url) for parallel opens.

        SLIDERS: [slider] elements are adjusted with drag(). browse_page() shows
        the current value after dragging (e.g. [7] [slider] Volume = 8).

        EFFICIENCY:
        - Stop when you have enough data — do NOT scroll for completeness.
        - Prefer site search/filters over scrolling through results.
        - Dismiss overlays early (click close/dismiss buttons).

        TEXT-ONLY READING (fast path):
        When you already have a URL, fetch_url(url) reads it as text with no
        browser. It returns the page content inline and saves the full page
        to a file; if the result is marked truncated, read the rest of that
        file with run_bash_cmd (grep, sed, cat).
        Use the browser (goto + read_page / browse_page) when:
        - fetch_url returns a blocked / bot-challenge / failed message,
        - the page needs JavaScript rendering or interactive navigation, or
        - you need to search for a page rather than read a known URL.

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
        elements have clear refs. Use vision tools (browser_visual_action,
        inspect_page) when:
        - Elements have no ref (canvas, images, CAPTCHAs, custom widgets)
        - A ref-based action failed
        - You need to answer a question about what the page looks like

        WHEN STUCK:
        - Ref not found → page may have changed, call browse_page() for fresh refs
        - Can't find element → scroll + browse_page, or browse_page(scope="...")
        - Ref failed → try browser_visual_action("describe what to do")
        - Page too complex → save_page_content("page.md") + run_bash_cmd("grep ...")
    """),
    tools=[
        goto,
        new_tab,
        close_tab,
        browse_page,
        read_page,
        click,
        press_and_hold,
        browser_visual_action,
        fill_field,
        press_keys,
        select_option,
        scroll_page,
        go_back,
        drag,
        inspect_page,
        execute_javascript,
        save_page_content,
        fetch_url,
        run_bash_cmd,
    ],
)
