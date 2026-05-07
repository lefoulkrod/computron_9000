"""E2E tests for the wizard's provider selection step.

These run after the initial setup wizard has completed (via the autouse
fixture). They re-open the wizard via Settings > System > Run Setup
Wizard, then exercise the provider step UI.
"""

from contextlib import contextmanager

from playwright.sync_api import Page, expect


@contextmanager
def _rerun_wizard(page: Page):
    """Open the wizard via the Settings UI."""
    page.goto("/")
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("button", name="System").click()
    page.get_by_role("button", name="Run Setup Wizard").click()
    page.get_by_text("Welcome to Computron").wait_for(state="visible", timeout=10_000)
    try:
        yield
    finally:
        page.goto("/")


def _open_provider_step(page: Page):
    """Advance from Welcome to the provider step."""
    page.get_by_role("button", name="Get Started").click()
    page.get_by_text("Choose your LLM provider").wait_for(state="visible")


# ── Provider field visibility ────────────────────────────────────────


def test_ollama_shows_url_field(page: Page):
    """Selecting Ollama shows only the URL field."""
    with _rerun_wizard(page):
        _open_provider_step(page)
        page.get_by_text("Ollama (local)").click()

        expect(page.locator("#ollama-url")).to_be_visible()
        expect(page.locator("#compat-url")).not_to_be_visible()
        expect(page.locator("#compat-key")).not_to_be_visible()
        expect(page.locator("#cloud-provider")).not_to_be_visible()
        expect(page.locator("#cloud-key")).not_to_be_visible()


def test_compat_shows_url_and_key_fields(page: Page):
    """Selecting OpenAI-compatible shows URL and optional API key."""
    with _rerun_wizard(page):
        _open_provider_step(page)
        page.get_by_text("OpenAI-compatible endpoint").click()

        expect(page.locator("#compat-url")).to_be_visible()
        expect(page.locator("#compat-key")).to_be_visible()
        expect(page.locator("#ollama-url")).not_to_be_visible()
        expect(page.locator("#cloud-provider")).not_to_be_visible()


def test_cloud_shows_provider_select_and_key(page: Page):
    """Selecting Cloud API shows provider dropdown and API key."""
    with _rerun_wizard(page):
        _open_provider_step(page)
        page.get_by_role("button", name="Cloud API").click()

        expect(page.locator("#cloud-provider")).to_be_visible()
        expect(page.locator("#cloud-key")).to_be_visible()
        expect(page.locator("#ollama-url")).not_to_be_visible()
        expect(page.locator("#compat-url")).not_to_be_visible()


def test_cloud_dropdown_has_all_providers(page: Page):
    """The cloud provider dropdown includes Anthropic, OpenAI, and OpenRouter."""
    with _rerun_wizard(page):
        _open_provider_step(page)
        page.get_by_role("button", name="Cloud API").click()

        select = page.locator("#cloud-provider")
        options = select.locator("option").all_text_contents()
        assert "Anthropic" in options
        assert "OpenAI" in options
        assert "OpenRouter" in options


def test_switching_provider_hides_previous_fields(page: Page):
    """Fields from a previously selected provider disappear."""
    with _rerun_wizard(page):
        _open_provider_step(page)

        page.get_by_text("Ollama (local)").click()
        expect(page.locator("#ollama-url")).to_be_visible()

        page.get_by_role("button", name="Cloud API").click()
        expect(page.locator("#ollama-url")).not_to_be_visible()
        expect(page.locator("#cloud-provider")).to_be_visible()
