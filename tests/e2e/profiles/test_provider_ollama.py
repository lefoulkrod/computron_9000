"""E2E tests: Ollama provider field visibility and presets."""

import re

from playwright.sync_api import expect

from tests.e2e.pages import SettingsPage


OLLAMA_FIELDS = ("temperature", "top_k", "top_p", "repeat_penalty", "context_window", "num_predict", "max_iterations", "think")


def test_ollama_shows_all_fields(page, provider_profile):
    """All inference fields are visible when the provider is Ollama."""
    provider_profile("test_prov_ollama_all", "ollama")

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_ollama_all")
    settings.builder.open_advanced()

    for name in OLLAMA_FIELDS:
        expect(settings.builder.field(name)).to_be_visible()


def test_ollama_code_preset(page, provider_profile):
    """Code preset on Ollama sets temperature=0.3 and think=true."""
    provider_profile("test_prov_ollama_code", "ollama", temperature=0.3, think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_ollama_code")

    expect(settings.builder.preset("Code")).to_have_class(re.compile(r"presetActive"))


def test_ollama_hides_reasoning_fields(page, provider_profile):
    """Reasoning effort/summary and thinking budget are not shown for Ollama."""
    provider_profile("test_prov_ollama_reason", "ollama", think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_ollama_reason")
    settings.builder.open_advanced()

    expect(settings.builder.field("reasoning_effort")).not_to_be_attached()
    expect(settings.builder.field("reasoning_summary")).not_to_be_attached()
    expect(settings.builder.field("thinking_budget")).not_to_be_attached()
