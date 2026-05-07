"""E2E tests: provider-aware visibility for vision advanced settings."""

from playwright.sync_api import Page, expect

from e2e.pages import SettingsPage


def _set_provider(page: Page, provider: str) -> None:
    page.request.put("/api/settings", data={"llm_provider": provider})


def test_ollama_shows_all_vision_options(page: Page):
    """All vision option fields are visible when the provider is Ollama."""
    _set_provider(page, "ollama")
    settings = SettingsPage(page).goto_system()
    settings.system.open_vision_advanced()

    for key in ("temperature", "top_k", "top_p", "num_ctx", "num_predict"):
        expect(settings.system.vision_option(key)).to_be_visible()


def test_openai_hides_top_k_and_num_ctx(page: Page):
    """OpenAI does not support top_k or num_ctx for vision."""
    _set_provider(page, "openai")

    try:
        settings = SettingsPage(page).goto_system()
        settings.system.open_vision_advanced()

        for key in ("temperature", "top_p", "num_predict"):
            expect(settings.system.vision_option(key)).to_be_visible()

        for key in ("top_k", "num_ctx"):
            expect(settings.system.vision_option(key)).not_to_be_attached()
    finally:
        _set_provider(page, "ollama")


def test_anthropic_shows_top_k_hides_num_ctx(page: Page):
    """Anthropic supports top_k but not num_ctx."""
    _set_provider(page, "anthropic")

    try:
        settings = SettingsPage(page).goto_system()
        settings.system.open_vision_advanced()

        for key in ("temperature", "top_k", "top_p", "num_predict"):
            expect(settings.system.vision_option(key)).to_be_visible()

        expect(settings.system.vision_option("num_ctx")).not_to_be_attached()
    finally:
        _set_provider(page, "ollama")
