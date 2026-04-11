"""E2E test for creating an agent profile through the settings UI."""

from playwright.sync_api import Page, expect


def test_create_profile_persists_all_settings(page: Page):
    """Create a new profile via the UI, fill in all fields, save, and verify via API."""
    page.goto("/")

    # Open settings
    page.get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Agent Profiles")).to_be_visible()

    # Click "+ New" to create a profile
    page.get_by_role("button", name="+ New").click()

    # The new profile should appear selected — wait for the editor to load
    name_input = page.locator("input[placeholder='Profile name']")
    name_input.wait_for(state="visible")

    # --- Fill in identity ---
    name_input.fill("")
    name_input.fill("Test Agent")
    page.locator("input[placeholder='Short description']").fill("A test profile created by e2e")

    # Pick an icon
    page.locator("[class*='iconPicker']").click()
    page.locator("[class*='emojiOption']").first.click()

    # --- Pick a model (first available) ---
    model_select = page.locator("select").first
    model_options = model_select.locator("option").all()
    # Skip the first option ("Inherit from default agent")
    selected_model = ""
    if len(model_options) > 1:
        selected_model = model_options[1].get_attribute("value")
        model_select.select_option(selected_model)

    # --- System prompt ---
    page.locator("textarea[placeholder='System prompt...']").fill("You are a test agent.")

    # --- Toggle a skill (first available) ---
    skill_buttons = page.locator("button[class*='chip']")
    first_skill = None
    if skill_buttons.count() > 0:
        first_skill = skill_buttons.first.inner_text().strip()
        skill_buttons.first.click()

    # --- Pick an inference preset (Creative) ---
    page.locator("[class*='presetBtn']", has_text="Creative").click()

    # --- Open advanced settings and set values ---
    page.get_by_text("Advanced Settings").click()

    # Set context window
    ctx_input = page.locator("input[placeholder='auto']").nth(0)  # Temperature
    # Clear and set temperature explicitly to verify it overrides the preset
    ctx_input.fill("0.8")

    # Set context window (num_ctx)
    page.locator("input[placeholder='auto']").nth(4).fill("16000")

    # Set max output (num_predict)
    page.locator("input[placeholder='unlimited']").first.fill("4096")

    # --- Save ---
    page.get_by_role("button", name="Save").click()

    # --- Verify via API ---
    # Give the save a moment to persist
    page.wait_for_timeout(500)

    profiles = page.request.get("/api/profiles").json()
    created = next((p for p in profiles if p["name"] == "Test Agent"), None)
    assert created is not None, f"Profile 'Test Agent' not found in {[p['name'] for p in profiles]}"

    # Identity
    assert created["name"] == "Test Agent"
    assert created["description"] == "A test profile created by e2e"
    assert created["icon"]  # Should have an icon set

    # Model
    if selected_model:
        assert created["model"] == selected_model

    # System prompt
    assert created["system_prompt"] == "You are a test agent."

    # Skills
    if first_skill:
        assert first_skill in created.get("skills", []), (
            f"Expected '{first_skill}' in skills, got {created.get('skills')}"
        )

    # Inference params — temperature was overridden to 0.8
    assert created["temperature"] == 0.8

    # Advanced settings
    assert created["num_ctx"] == 16000
    assert created["num_predict"] == 4096

    # Clean up — delete the test profile
    profile_id = created["id"]
    resp = page.request.delete(f"/api/profiles/{profile_id}")
    assert resp.status == 204
