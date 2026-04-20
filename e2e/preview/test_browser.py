"""E2E test for the agent's browser tool.

Asks the agent to navigate to example.com and verifies that the browser
tool actually launched Chrome (a browser preview tab appears in the UI)
and that the page content was read (the assistant's reply mentions the
distinctive page title).

Catches container/permissions regressions where Chrome can't start under
the `computron` user — e.g. the chown-after-mkdir bug in entrypoint.sh
that left ~/.config root-owned.
"""

import pytest
from playwright.sync_api import Page, expect

from e2e.pages import ChatView

LLM_TIMEOUT = 180_000


@pytest.fixture(scope="module")
def browsed(browser, browser_context_args):
    """Ask the agent to browse to example.com once for all tests in the module."""
    context = browser.new_context(**browser_context_args)
    page = context.new_page()

    chat = ChatView(page).goto().new_conversation()
    chat.send(
        "browse to https://example.com and tell me the page title",
    ).wait_streaming(timeout=LLM_TIMEOUT)

    yield page

    page.close()
    context.close()


def test_browser_preview_tab_appears(browsed: Page):
    """A browser preview tab appears once the agent has loaded the page.

    If Chrome failed to launch (e.g. crashpad couldn't write to ~/.config),
    no browser snapshot would be emitted and this tab would never render.
    """
    chat = ChatView(browsed)
    expect(chat.preview.browser_tab).to_be_visible(timeout=10_000)


def test_browser_page_title_in_response(browsed: Page):
    """The assistant's reply quotes 'Example Domain' — proves the page was read.

    Tab visibility alone could be triggered by a navigation that errored
    before content load. Asserting the title text in the chat confirms
    the agent actually got the page back, not just an error placeholder.
    """
    expect(browsed.get_by_text("Example Domain").first).to_be_visible()
