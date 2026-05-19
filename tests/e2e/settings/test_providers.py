"""E2E tests for the Providers settings tab.

These tests don't create brokered providers (anthropic/openai/openrouter)
because those need real API keys. They do exercise the verification flows
— catalog filtering, modal open/close, Test connection, and a remove +
re-add round-trip on Ollama so the rest of the suite still has its
provider configured when these finish.
"""

from playwright.sync_api import Page, expect

from tests.e2e.pages import SettingsPage


def test_providers_tab_shows_seeded_ollama(page: Page):
    """The wizard configured Ollama; the tab should list it."""
    SettingsPage(page).goto_providers()

    row = page.get_by_test_id("provider-row-ollama")
    expect(row).to_be_visible()


def test_add_modal_opens_from_add_button(page: Page):
    """Clicking 'Add' opens the catalog modal."""
    SettingsPage(page).goto_providers()

    page.get_by_test_id("providers-add-btn").click()
    expect(page.get_by_test_id("add-provider-modal")).to_be_visible()


def test_catalog_excludes_already_configured_provider(page: Page):
    """Ollama is already configured, so its catalog card shouldn't appear."""
    SettingsPage(page).goto_providers()
    page.get_by_test_id("providers-add-btn").click()

    expect(page.get_by_test_id("provider-catalog-card-ollama")).to_have_count(0)
    # The four others should all still be available.
    for name in ("openai_compat", "anthropic", "openai", "openrouter"):
        expect(page.get_by_test_id(f"provider-catalog-card-{name}")).to_be_visible()


def test_add_modal_cancel_closes_it(page: Page):
    """Cancel button in the catalog step dismisses the modal."""
    SettingsPage(page).goto_providers()
    page.get_by_test_id("providers-add-btn").click()
    expect(page.get_by_test_id("add-provider-modal")).to_be_visible()

    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_test_id("add-provider-modal")).to_have_count(0)


def test_continue_disabled_until_card_selected(page: Page):
    """Continue button is disabled in the catalog step until a card is picked."""
    SettingsPage(page).goto_providers()
    page.get_by_test_id("providers-add-btn").click()

    cont = page.get_by_test_id("provider-catalog-continue-btn")
    expect(cont).to_be_disabled()
    page.get_by_test_id("provider-catalog-card-anthropic").click()
    expect(cont).to_be_enabled()

    page.get_by_role("button", name="Cancel").click()


def test_test_connection_succeeds_for_ollama(page: Page):
    """Test connection on the seeded Ollama provider returns a model count."""
    SettingsPage(page).goto_providers()
    page.get_by_test_id("provider-row-ollama").click()
    page.get_by_test_id("provider-test-btn").click()

    page.get_by_text("Connected · ", exact=False).wait_for(state="visible", timeout=15_000)


def test_remove_and_re_add_ollama(page: Page):
    """Remove the Ollama provider, verify empty state, then add it back.

    This restores the suite's invariant (Ollama configured) so later tests
    don't break. Keep this test self-contained: never split the remove and
    re-add into separate tests.
    """
    settings = SettingsPage(page).goto_providers()

    # Remove. ConfirmButton: first click arms, second click fires.
    page.get_by_test_id("provider-row-ollama").click()
    remove_btn = page.get_by_test_id("provider-remove-btn")
    remove_btn.click()
    page.get_by_role("button", name="Confirm remove?").click()

    # Empty state appears (no providers left).
    page.get_by_test_id("providers-empty-add-btn").wait_for(state="visible", timeout=10_000)

    # Server-side: /api/providers returns [].
    listing = page.request.get("/api/providers").json()
    assert listing.get("providers", []) == []

    # Add it back through the modal.
    page.get_by_test_id("providers-empty-add-btn").click()
    page.get_by_test_id("provider-catalog-card-ollama").click()
    page.get_by_test_id("provider-catalog-continue-btn").click()

    # The configure step pre-fills the default URL. Override to localhost so
    # it matches the wizard's setup (the e2e container uses --network=host).
    url_input = page.locator("#provider-url")
    url_input.fill("http://localhost:11434")
    page.get_by_test_id("provider-configure-submit-btn").click()

    # The row should reappear in the list.
    page.get_by_test_id("provider-row-ollama").wait_for(state="visible", timeout=15_000)

    # Server-side: /api/providers lists ollama again.
    listing = page.request.get("/api/providers").json()
    names = [p["name"] for p in listing.get("providers", [])]
    assert "ollama" in names
    _ = settings  # POM kept for future assertions if added
