Goal
Let the agent bring off-screen content into view and trigger lazy-loading by scrolling the page in a controlled way.

Proposed Function

async def scroll_page(direction: str = "down", amount: int | None = None) -> PageSnapshot:
    """Scroll the page in the given direction and return the updated page snapshot.

    Args:
        direction: One of {"down", "up", "page_down", "page_up", "top", "bottom"}.
            Defaults to "down".
        amount: Optional pixel distance for fine-grained scrolling when direction
            is "down" or "up". If omitted, a viewport-sized scroll (page-style)
            is performed.

    Returns:
        PageSnapshot: Snapshot of the page state after scrolling.

    Raises:
        BrowserToolError: If direction is invalid or the page is not navigated.
    """
Implementation Outline

Validate and normalize direction / amount.
Ensure the current page is navigated and retrieve it via get_browser().
Use the human interaction layer (extend it with human_scroll) to perform smooth scrolling based on config jitter:
For "top"/"bottom" call page.keyboard.press("Home"/"End") or page.evaluate("window.scrollTo...").
For step scrolls (down/up) use mouse wheel or keyboard PageDown.
Return a fresh PageSnapshot so the agent sees newly loaded content.
Follow-up considerations

Expose the tool through the browser agent prompt, describing directions in plain terms (“Scrolls the page up/down/top/bottom; optional pixel amount for finer control”).
Add unit tests that monkeypatch human_scroll to assert direction validation and snapshot return.
With open_url + click + fill_field + press_keys (planned) + scroll_page, the agent can navigate, interact, and reveal content effectively.

