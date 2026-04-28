"""E2E test for creating an agent profile through the settings UI.

Verifies that every field in the profile builder persists correctly.
The API reads profiles from JSON files on disk (no in-memory cache),
so asserting via the API proves disk persistence.
"""

from playwright.sync_api import Page

from e2e.pages import SettingsPage


def test_create_profile_persists_all_settings(page: Page):
    """Create a new profile via the UI, set every field, save, and verify via API."""
    settings = SettingsPage(page).goto()
    settings.profiles.new()
    builder = settings.builder

    # --- Identity ---
    builder.name_input.fill("")
    builder.name_input.fill("Test Agent")
    builder.description_input.fill("A test profile created by e2e")

    # --- Model (first available) ---
    model_options = builder.model_select.locator("option").all()
    selected_model = model_options[0].get_attribute("value") if model_options else ""
    if selected_model:
        builder.model_select.select_option(selected_model)

    # --- System prompt ---
    builder.system_prompt.fill("You are a test agent.")

    # --- Skills (toggle first available) ---
    first_skill = None
    if builder.skill_chips.count() > 0:
        first_skill = builder.skill_chips.first.inner_text().strip()
        builder.skill_chips.first.click()

    # --- Advanced settings (set every inference field) ---
    builder.open_advanced()
    builder.auto_field(0).fill("0.8")       # Temperature
    builder.auto_field(1).fill("50")        # Top K
    builder.auto_field(2).fill("0.9")       # Top P
    builder.auto_field(3).fill("1.2")       # Repeat Penalty
    builder.auto_field(4).fill("16000")     # num_ctx
    builder.unlimited_field(0).fill("4096") # num_predict
    builder.unlimited_field(1).fill("25")   # max_iterations
    page.locator("label", has_text="Thinking").click()

    # --- Save ---
    builder.save()
    page.wait_for_timeout(500)

    # --- Verify via API (reads from disk, no cache) ---
    profiles = page.request.get("/api/profiles").json()
    created = next((p for p in profiles if p["name"] == "Test Agent"), None)
    assert created is not None, f"Profile 'Test Agent' not found in {[p['name'] for p in profiles]}"

    # Identity
    assert created["name"] == "Test Agent"
    assert created["description"] == "A test profile created by e2e"

    # Model
    if selected_model:
        assert created["model"] == selected_model

    # System prompt
    assert created["system_prompt"] == "You are a test agent."

    # Skills
    if first_skill:
        assert first_skill in created["skills"], (
            f"Expected '{first_skill}' in skills, got {created['skills']}"
        )

    # Inference params
    assert created["temperature"] == 0.8
    assert created["top_k"] == 50
    assert created["top_p"] == 0.9
    assert created["repeat_penalty"] == 1.2
    assert created["think"] is True

    # Resource limits
    assert created["num_ctx"] == 16000
    assert created["num_predict"] == 4096
    assert created["max_iterations"] == 25

    # Clean up — delete the test profile
    resp = page.request.delete(f"/api/profiles/{created['id']}")
    assert resp.status == 204


def test_new_button_does_not_persist_until_save(page: Page):
    """Clicking + New opens the builder without writing anything to disk."""
    before = {p["id"] for p in page.request.get("/api/profiles").json()}

    settings = SettingsPage(page).goto()
    settings.profiles.new()

    # Discard the draft by selecting an existing profile.
    page.locator("[data-testid^='profile-item-']").first.click()

    after = {p["id"] for p in page.request.get("/api/profiles").json()}
    assert before == after, "A profile was persisted without clicking Save"
