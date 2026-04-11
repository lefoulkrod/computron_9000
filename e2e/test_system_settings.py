"""E2E tests for system settings page."""

from playwright.sync_api import Page


def _open_system_settings(page: Page):
    """Navigate to Settings > System tab."""
    page.goto("/")
    page.locator("button[title='Settings']").click()
    page.get_by_role("button", name="System").click()
    # Wait for the system settings to load (Ollama connection status appears)
    page.locator("[class*='settingRow']").first.wait_for(state="visible")


def test_change_default_agent(page: Page):
    """Change the default agent and verify it persists."""
    _open_system_settings(page)

    # Default agent is the first select
    default_select = page.locator("select").first
    options = default_select.locator("option").all()
    assert len(options) >= 2, "Need at least 2 profiles to test switching"

    current = default_select.input_value()
    new_value = next(o.get_attribute("value") for o in options if o.get_attribute("value") != current)
    default_select.select_option(new_value)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["default_agent"] == new_value

    # Restore
    default_select.select_option(current)
    page.wait_for_timeout(500)


def test_change_vision_model(page: Page):
    """Change the vision model and verify it persists."""
    _open_system_settings(page)

    vision_select = page.locator("select").nth(1)
    options = vision_select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 vision model"

    original = vision_select.input_value()
    new_model = options[1].get_attribute("value")
    vision_select.select_option(new_model)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["vision_model"] == new_model

    # Restore
    if original:
        vision_select.select_option(original)
        page.wait_for_timeout(500)


def test_change_compaction_model(page: Page):
    """Change the compaction model and verify it persists."""
    _open_system_settings(page)

    compaction_select = page.locator("select").nth(2)
    options = compaction_select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 model for compaction"

    original = compaction_select.input_value()
    new_model = options[1].get_attribute("value")
    compaction_select.select_option(new_model)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["compaction_model"] == new_model

    # Restore
    if original:
        compaction_select.select_option(original)
        page.wait_for_timeout(500)
