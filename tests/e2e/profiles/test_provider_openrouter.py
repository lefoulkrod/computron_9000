"""E2E tests: OpenRouter provider field visibility and presets."""

import re

from playwright.sync_api import expect

from tests.e2e.pages import SettingsPage


VISIBLE_FIELDS = ("temperature", "top_p", "num_predict", "max_iterations", "think")
HIDDEN_FIELDS = ("top_k", "repeat_penalty", "num_ctx")


def test_openrouter_field_visibility(page, provider_profile):
    """OpenRouter shows think toggle but hides Ollama-only fields."""
    provider_profile("test_prov_or_vis", "openrouter")

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_or_vis")
    settings.builder.open_advanced()

    for name in VISIBLE_FIELDS:
        expect(settings.builder.field(name)).to_be_visible()
    for name in HIDDEN_FIELDS:
        expect(settings.builder.field(name)).not_to_be_attached()


def test_openrouter_code_preset(page, provider_profile):
    """Code preset on OpenRouter sets temperature=0.3 and think=true."""
    provider_profile("test_prov_or_code", "openrouter", temperature=0.3, think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_or_code")

    expect(settings.builder.preset("Code")).to_have_class(re.compile(r"presetActive"))


def test_openrouter_reasoning_fields_with_think(page, provider_profile):
    """OpenRouter shows reasoning_effort when think is enabled."""
    provider_profile("test_prov_or_reason", "openrouter", think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_or_reason")
    settings.builder.open_advanced()

    expect(settings.builder.field("reasoning_effort")).to_be_visible()
    expect(settings.builder.field("reasoning_summary")).not_to_be_attached()
    expect(settings.builder.field("thinking_budget")).not_to_be_attached()
