"""E2E tests for preview panel tab lifecycle.

Verifies that preview tabs appear when content arrives, can be switched
between, and close cleanly.

Uses a single conversation to avoid redundant LLM calls.
"""

import pytest
from playwright.sync_api import Page, expect

LLM_TIMEOUT = 180_000


def _send_message(page: Page, text: str):
    """Type a message and press Enter."""
    textarea = page.locator("textarea")
    textarea.fill(text)
    textarea.press("Enter")


def _wait_for_streaming_done(page: Page, timeout: int = LLM_TIMEOUT):
    """Wait until the assistant finishes streaming (stop button disappears)."""
    stop_btn = page.locator("button[title='Stop generation']")
    try:
        stop_btn.wait_for(state="visible", timeout=10_000)
    except Exception:
        pass  # May have already finished
    stop_btn.wait_for(state="hidden", timeout=timeout)


def _start_new_conversation(page: Page):
    """Click the new conversation button to reset state."""
    page.locator("button[title='New conversation']").click()
    page.wait_for_timeout(500)


@pytest.fixture(scope="module")
def preview_page(browser, browser_context_args):
    """Set up a conversation that produces browser, terminal, and file tabs.

    Sends a single explicit prompt that triggers all preview types, then
    clicks Preview on a file output to open a file tab.
    """
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    page.goto("/")
    _start_new_conversation(page)

    _send_message(
        page,
        'to enable e2e testing do the following: '
        'run echo "hello" on the command line, '
        'create a simple text file called hello.txt that says "hello" '
        'and send it to me',
    )
    _wait_for_streaming_done(page)

    # We expect at least a terminal tab from the echo command
    has_terminal = page.get_by_test_id("preview-tab-terminal").is_visible()
    has_file_btn = page.get_by_test_id("file-preview-btn").first.is_visible()

    assert has_terminal or has_file_btn, (
        "Agent did not produce any preview content"
    )

    # If file preview button exists, click it to open a file tab
    if has_file_btn:
        page.get_by_test_id("file-preview-btn").first.click()
        page.locator("[data-testid^='preview-tab-file:']").first.wait_for(
            state="visible", timeout=5_000,
        )

    yield page

    page.close()
    context.close()


# ── Tab appearance ──────────────────────────────────────────────────


def test_preview_panel_visible(preview_page: Page):
    """Preview panel should be mounted when tabs exist."""
    expect(preview_page.get_by_test_id("preview-panel")).to_be_visible()


def test_split_handle_visible(preview_page: Page):
    """Split handle should be visible when preview panel is open."""
    expect(preview_page.locator("[role='separator']")).to_be_visible()


def test_at_least_one_tab_visible(preview_page: Page):
    """At least one preview tab should be visible."""
    tab_bar = preview_page.get_by_test_id("preview-tab-bar")
    tabs = tab_bar.locator("button")
    assert tabs.count() >= 1


# ── Tab switching ───────────────────────────────────────────────────


def test_clicking_tab_shows_content(preview_page: Page):
    """Clicking a tab should show content in the preview area."""
    tab_bar = preview_page.get_by_test_id("preview-tab-bar")
    first_tab = tab_bar.locator("button").first
    first_tab.click()
    preview_page.wait_for_timeout(200)

    content = preview_page.get_by_test_id("preview-content")
    expect(content).to_be_visible()


def test_switch_between_tabs(preview_page: Page):
    """Switching between tabs shows different content."""
    tab_bar = preview_page.get_by_test_id("preview-tab-bar")
    tabs = tab_bar.locator("button")
    assert tabs.count() >= 2, "Expected at least 2 preview tabs"

    tabs.nth(1).click()
    preview_page.wait_for_timeout(200)
    expect(preview_page.get_by_test_id("preview-content")).to_be_visible()

    tabs.nth(0).click()
    preview_page.wait_for_timeout(200)
    expect(preview_page.get_by_test_id("preview-content")).to_be_visible()


# ── Tab closing ─────────────────────────────────────────────────────


def test_close_tab(preview_page: Page):
    """Closing a tab removes it from the tab bar."""
    tab_bar = preview_page.get_by_test_id("preview-tab-bar")
    initial_count = tab_bar.locator("button").count()

    first_tab = tab_bar.locator("button").first
    first_tab.locator("[class*='tabClose']").click()

    new_count = tab_bar.locator("button").count()
    assert new_count == initial_count - 1


def test_close_all_tabs_hides_preview(preview_page: Page):
    """After closing all tabs, the preview panel and split handle vanish."""
    tab_bar = preview_page.get_by_test_id("preview-tab-bar")

    while tab_bar.locator("button").count() > 0:
        tab_bar.locator("button").first.locator("[class*='tabClose']").click()
        preview_page.wait_for_timeout(200)

    expect(preview_page.locator("[role='separator']")).not_to_be_visible()
    expect(preview_page.get_by_test_id("preview-panel")).not_to_be_visible()
