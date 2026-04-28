"""E2E test: new profile appears in the chat panel's profile dropdown."""

from playwright.sync_api import Page, expect

from e2e.pages import SettingsPage


def test_new_profile_appears_in_chat_dropdown(page: Page):
    """Create a profile via settings, verify it shows up in the chat selector."""
    settings = SettingsPage(page).goto()
    settings.profiles.new()

    settings.builder.name_input.fill("")
    settings.builder.name_input.fill("Dropdown Test Agent")
    settings.builder.save()
    page.wait_for_timeout(500)

    # Close settings and check the chat panel's profile dropdown
    settings.close()
    chat_selector = page.get_by_label("Agent profile")
    expect(chat_selector).to_be_visible()
    option = chat_selector.locator("option", has_text="Dropdown Test Agent")
    expect(option).to_be_attached()

    # Clean up
    profiles = page.request.get("/api/profiles").json()
    created = next(p for p in profiles if p["name"] == "Dropdown Test Agent")
    page.request.delete(f"/api/profiles/{created['id']}")
