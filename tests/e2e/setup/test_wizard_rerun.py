"""E2E tests for re-running the setup wizard.

These verify the re-run-specific behavior: the "Update all agent
profiles" checkbox on the model step, and that skipping vision clears
the vision_model setting.

A module-scoped fixture snapshots profiles and settings before this
module runs and restores them in a finalizer, so downstream tests
still see the models chosen by the session setup fixture.
"""

import json

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import BASE_URL


def _put_json(page, url, data):
    """PUT JSON to an API endpoint."""
    return page.request.put(url, data=json.dumps(data))


@pytest.fixture(scope="module", autouse=True)
def _restore_state(browser):
    """Snapshot profiles and settings before the module, restore after."""
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()

    settings_snapshot = page.request.get("/api/settings").json()
    profiles_snapshot = page.request.get("/api/profiles").json()

    page.close()
    context.close()

    yield

    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()

    _put_json(page, "/api/settings", settings_snapshot)

    for profile in profiles_snapshot:
        _put_json(page, f"/api/profiles/{profile['id']}", {"model": profile["model"]})

    page.close()
    context.close()


def _reset_and_open_wizard(page: Page):
    """Trigger the wizard via Settings > System > Run Setup Wizard."""
    page.goto("/")
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("button", name="System").click()
    page.get_by_role("button", name="Run Setup Wizard").click()
    page.get_by_text("Welcome to Computron").wait_for(state="visible", timeout=10_000)


def _advance_past_provider(page: Page):
    """Click through Welcome and Provider steps (Ollama, default URL)."""
    page.get_by_role("button", name="Get Started").click()
    page.get_by_text("Choose your LLM provider").wait_for(state="visible")
    page.get_by_text("Ollama (local)").click()
    page.locator("#ollama-url").fill("http://localhost:11434")
    page.get_by_role("button", name="Connect").click()
    page.get_by_text("Choose your main model").wait_for(state="visible", timeout=15_000)


def _pick_first_model(page: Page):
    """Select the first model in the ModelPicker."""
    items = page.get_by_test_id("model-item")
    items.first.wait_for(state="visible", timeout=15_000)
    name = items.first.get_attribute("data-model-name")
    items.first.click()
    return name


def _finish_wizard(page: Page):
    """Click through from the Ready step to completion."""
    page.get_by_text("You're all set").wait_for(state="visible")
    page.get_by_role("button", name="Start Chatting").click()
    page.wait_for_function(
        """async () => {
            const r = await fetch('/api/settings');
            const s = await r.json();
            return s.setup_complete === true;
        }""",
        timeout=10_000,
    )


# ── Profile update checkbox ──────────────────────────────────────────


def test_rerun_shows_update_profiles_checkbox(page: Page):
    """On re-run, the model step shows the update-all-profiles checkbox."""
    _reset_and_open_wizard(page)
    _advance_past_provider(page)

    checkbox = page.get_by_test_id("update-profiles-check").locator("input[type='checkbox']")
    expect(checkbox).to_be_visible()
    expect(checkbox).to_be_checked()

    # Restore setup_complete without finishing the wizard — the module
    # fixture will restore full state, but the server needs the flag back.
    _put_json(page, "/api/settings", {"setup_complete": True})
    page.goto("/")


def test_rerun_updates_all_profiles_when_checked(page: Page):
    """With the checkbox checked, all profiles get the new model."""
    _reset_and_open_wizard(page)
    _advance_past_provider(page)

    new_model = _pick_first_model(page)

    checkbox = page.get_by_test_id("update-profiles-check").locator("input[type='checkbox']")
    if not checkbox.is_checked():
        checkbox.click()

    page.get_by_role("button", name="Continue").click()

    # Vision step — skip it
    page.get_by_text("Choose a vision model").wait_for(state="visible")
    page.get_by_text("Skip").click()
    page.get_by_role("button", name="Continue").click()

    _finish_wizard(page)

    profiles_after = page.request.get("/api/profiles").json()
    for profile in profiles_after:
        assert profile["model"] == new_model, (
            f"Profile '{profile['id']}' has model '{profile['model']}', "
            f"expected '{new_model}'"
        )


def test_rerun_preserves_profiles_when_unchecked(page: Page):
    """With the checkbox unchecked, existing profile models are preserved."""
    profiles_before = page.request.get("/api/profiles").json()
    models_before = {p["id"]: p["model"] for p in profiles_before}

    _reset_and_open_wizard(page)
    _advance_past_provider(page)

    _pick_first_model(page)

    checkbox = page.get_by_test_id("update-profiles-check").locator("input[type='checkbox']")
    if checkbox.is_checked():
        checkbox.click()

    page.get_by_role("button", name="Continue").click()

    # Vision step — skip it
    page.get_by_text("Choose a vision model").wait_for(state="visible")
    page.get_by_text("Skip").click()
    page.get_by_role("button", name="Continue").click()

    _finish_wizard(page)

    profiles_after = page.request.get("/api/profiles").json()
    for profile in profiles_after:
        if profile["id"] in models_before and models_before[profile["id"]]:
            assert profile["model"] == models_before[profile["id"]], (
                f"Profile '{profile['id']}' changed from "
                f"'{models_before[profile['id']]}' to '{profile['model']}'"
            )


# ── Vision skip ──────────────────────────────────────────────────────


def test_vision_skip_clears_setting(page: Page):
    """Skipping the vision step sets vision_model to null."""
    _reset_and_open_wizard(page)
    _advance_past_provider(page)
    _pick_first_model(page)
    page.get_by_role("button", name="Continue").click()

    # Vision step — skip
    page.get_by_text("Choose a vision model").wait_for(state="visible")
    page.get_by_text("Skip").click()
    page.get_by_role("button", name="Continue").click()

    _finish_wizard(page)

    settings_after = page.request.get("/api/settings").json()
    assert settings_after.get("vision_model") is None, (
        f"Expected vision_model to be null after skip, "
        f"got '{settings_after.get('vision_model')}'"
    )


def test_vision_selection_persists(page: Page):
    """Picking a vision model persists it in settings."""
    _reset_and_open_wizard(page)
    _advance_past_provider(page)
    _pick_first_model(page)
    page.get_by_role("button", name="Continue").click()

    # Vision step — pick a model
    page.get_by_text("Choose a vision model").wait_for(state="visible")
    vision_model = _pick_first_model(page)
    page.get_by_role("button", name="Continue").click()

    _finish_wizard(page)

    settings_after = page.request.get("/api/settings").json()
    assert settings_after["vision_model"] == vision_model
