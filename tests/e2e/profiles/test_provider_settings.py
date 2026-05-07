"""E2E tests: provider-aware advanced settings visibility and preset detection."""

import re

from playwright.sync_api import Page, expect

from e2e.pages import SettingsPage


OLLAMA_ONLY_FIELDS = ("top_k", "repeat_penalty", "num_ctx")
OLLAMA_ANTHROPIC_FIELDS = ("top_k",)
UNIVERSAL_FIELDS = ("temperature", "top_p", "num_predict", "max_iterations")


def _set_provider(page: Page, provider: str) -> None:
    page.request.put("/api/settings", data={"llm_provider": provider})


def _create_test_profile(page: Page, profile_id: str, **overrides) -> None:
    models = page.request.get("/api/models").json().get("models", [])
    model_name = models[0]["name"] if models else ""
    data = {
        "id": profile_id,
        "name": f"Provider Test ({profile_id})",
        "description": "",
        "model": model_name,
        "system_prompt": "",
        "skills": [],
        **overrides,
    }
    page.request.post("/api/profiles", data=data)


def test_ollama_shows_all_fields(page: Page):
    """All inference fields are visible when the provider is Ollama."""
    profile_id = "test_provider_ollama"
    _set_provider(page, "ollama")
    _create_test_profile(page, profile_id)

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        settings.builder.open_advanced()

        for name in (*UNIVERSAL_FIELDS, *OLLAMA_ONLY_FIELDS):
            expect(settings.builder.field(name)).to_be_visible()
    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
        _set_provider(page, "ollama")


def test_openai_hides_ollama_only_fields(page: Page):
    """Top K, Repeat Penalty, and Context are hidden on OpenAI."""
    profile_id = "test_provider_openai"
    _set_provider(page, "openai")
    _create_test_profile(page, profile_id)

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        settings.builder.open_advanced()

        for name in UNIVERSAL_FIELDS:
            expect(settings.builder.field(name)).to_be_visible()

        for name in OLLAMA_ONLY_FIELDS:
            expect(settings.builder.field(name)).not_to_be_attached()
    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
        _set_provider(page, "ollama")


def test_anthropic_shows_top_k_hides_ollama_only(page: Page):
    """Anthropic supports Top K but not Repeat Penalty or Context."""
    profile_id = "test_provider_anthropic"
    _set_provider(page, "anthropic")
    _create_test_profile(page, profile_id)

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        settings.builder.open_advanced()

        for name in (*UNIVERSAL_FIELDS, *OLLAMA_ANTHROPIC_FIELDS):
            expect(settings.builder.field(name)).to_be_visible()

        for name in ("repeat_penalty", "num_ctx"):
            expect(settings.builder.field(name)).not_to_be_attached()
    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
        _set_provider(page, "ollama")


def test_preset_detected_with_filtered_fields(page: Page):
    """Code preset is detected on OpenAI even though top_k is hidden."""
    profile_id = "test_provider_preset"
    _set_provider(page, "openai")
    _create_test_profile(page, profile_id, temperature=0.3, think=True)

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)

        expect(settings.builder.preset("Code")).to_have_class(re.compile(r"presetActive"))

        for label in ["Balanced", "Creative", "Precise"]:
            expect(settings.builder.preset(label)).not_to_have_class(re.compile(r"presetActive"))
    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
        _set_provider(page, "ollama")


def test_anthropic_max_output_placeholder(page: Page):
    """Max Output field shows '16384' placeholder on Anthropic."""
    profile_id = "test_provider_placeholder"
    _set_provider(page, "anthropic")
    _create_test_profile(page, profile_id)

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        settings.builder.open_advanced()

        expect(settings.builder.field("num_predict")).to_have_attribute("placeholder", "16384")
    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
        _set_provider(page, "ollama")
