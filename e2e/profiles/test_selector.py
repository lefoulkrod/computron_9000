"""E2E test: new profile appears in the chat panel's profile dropdown."""

from playwright.sync_api import Page, expect


def test_new_profile_appears_in_chat_dropdown(page: Page):
    """Create a profile via settings, verify it shows up in the chat selector."""
    page.goto("/")

    # Open settings and create a new profile
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("button", name="Agent Profiles").wait_for(state="visible")
    page.get_by_role("button", name="+ New").click()

    name_input = page.locator("input[placeholder='Profile name']")
    name_input.wait_for(state="visible")
    name_input.fill("")
    name_input.fill("Dropdown Test Agent")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(500)

    # Close settings
    page.get_by_role("button", name="Settings", exact=True).click()

    # The chat panel's profile dropdown should contain the new profile
    chat_selector = page.get_by_label("Agent profile")
    expect(chat_selector).to_be_visible()
    option = chat_selector.locator("option", has_text="Dropdown Test Agent")
    expect(option).to_be_attached()

    # Clean up
    profiles = page.request.get("/api/profiles").json()
    created = next(p for p in profiles if p["name"] == "Dropdown Test Agent")
    page.request.delete(f"/api/profiles/{created['id']}")
