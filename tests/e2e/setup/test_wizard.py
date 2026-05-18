"""Post-condition tests for the setup wizard.

The wizard itself is driven by the autouse fixture in `e2e/_setup.py`
before any test runs. These tests verify that everything the wizard
should have persisted actually did.
"""

from playwright.sync_api import Page, expect


def test_app_loads_after_setup(page: Page):
    """After setup, the chat UI should load without showing the wizard."""
    page.goto("/")
    expect(page.get_by_text("Welcome to Computron")).not_to_be_visible()
    expect(page.locator("textarea")).to_be_visible()


def test_settings_setup_complete(page: Page):
    """The setup_complete flag should be true."""
    settings = page.request.get("/api/settings").json()
    assert settings["setup_complete"] is True


def test_settings_default_agent(page: Page):
    """The default agent should be set to computron."""
    settings = page.request.get("/api/settings").json()
    assert settings["default_agent"] == "computron"


def test_settings_direct_provider(page: Page):
    """Ollama should be configured as a direct provider with a base URL."""
    settings = page.request.get("/api/settings").json()
    direct = settings.get("direct_providers", {})
    assert "ollama" in direct
    assert direct["ollama"].get("base_url")


def test_settings_per_use_providers(page: Page):
    """Vision, compaction, and title each get a provider stamped by the wizard."""
    settings = page.request.get("/api/settings").json()
    assert settings["vision_provider"] == "ollama"
    assert settings["compaction_provider"] == "ollama"
    assert settings["title_provider"] == "ollama"


def test_settings_vision_model(page: Page, wizard_choices):
    """The vision model should match what was picked in the wizard."""
    settings = page.request.get("/api/settings").json()
    assert settings["vision_model"] == wizard_choices["vision_model"]


def test_settings_compaction_model(page: Page, wizard_choices):
    """The compaction model should be set to the main model."""
    settings = page.request.get("/api/settings").json()
    assert settings["compaction_model"] == wizard_choices["main_model"]


def test_settings_title_model(page: Page, wizard_choices):
    """The title model should be set to the main model (matches compaction)."""
    settings = page.request.get("/api/settings").json()
    assert settings["title_model"] == wizard_choices["main_model"]


def test_ootb_profiles_all_have_same_model(page: Page, wizard_choices):
    """All OOTB profiles should have the picked model + provider."""
    profiles = page.request.get("/api/profiles").json()
    ootb_ids = {"computron", "code_expert", "research_agent", "creative_writer"}
    for profile in profiles:
        if profile["id"] in ootb_ids:
            assert profile["model"] == wizard_choices["main_model"], (
                f"Profile '{profile['id']}' has model '{profile['model']}', "
                f"expected '{wizard_choices['main_model']}'"
            )
            assert profile.get("provider") == "ollama", (
                f"Profile '{profile['id']}' has provider '{profile.get('provider')}', "
                f"expected 'ollama'"
            )


def test_ootb_profiles_have_context_window(page: Page):
    """All OOTB profiles should have a non-zero context_window after setup."""
    profiles = page.request.get("/api/profiles").json()
    ootb_ids = {"computron", "code_expert", "research_agent", "creative_writer"}
    for profile in profiles:
        if profile["id"] in ootb_ids:
            ctx = profile.get("context_window")
            assert ctx and ctx > 0, (
                f"Profile '{profile['id']}' has context_window={ctx}, "
                f"expected a positive value from model metadata"
            )
