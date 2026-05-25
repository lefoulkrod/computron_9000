"""E2E tests for the collapsible navigation sidebar."""

from playwright.sync_api import Page, expect

from tests.e2e.pages import ChatView, Sidebar


def test_sidebar_collapses_and_expands(page: Page):
    """Toggling the sidebar flips its collapsed state."""
    ChatView(page).goto()
    sidebar = Sidebar(page)

    sidebar.set_collapsed(False)
    assert not sidebar.is_collapsed()

    sidebar.toggle.click()
    page.wait_for_timeout(250)
    assert sidebar.is_collapsed()

    sidebar.toggle.click()
    page.wait_for_timeout(250)
    assert not sidebar.is_collapsed()


def test_collapsed_state_persists_across_reload(page: Page):
    """The collapsed choice survives a page reload (localStorage-backed)."""
    ChatView(page).goto()
    sidebar = Sidebar(page)

    sidebar.set_collapsed(True)
    assert sidebar.is_collapsed()

    page.reload()
    expect(sidebar.root).to_have_attribute("data-collapsed", "true")

    sidebar.set_collapsed(False)
    page.reload()
    expect(sidebar.root).to_have_attribute("data-collapsed", "false")


def test_new_chat_button_is_reachable(page: Page):
    """The New chat button works in both collapsed and expanded states."""
    ChatView(page).goto()
    sidebar = Sidebar(page)

    sidebar.set_collapsed(False)
    expect(sidebar.new_chat).to_be_visible()

    sidebar.set_collapsed(True)
    expect(sidebar.new_chat).to_be_visible()
