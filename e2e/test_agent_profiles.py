"""E2E test for creating an agent profile through the settings UI.

Verifies that every field in the profile builder persists correctly.
The API reads profiles from JSON files on disk (no in-memory cache),
so asserting via the API proves disk persistence.
"""

from playwright.sync_api import Page, expect


def test_create_profile_persists_all_settings(page: Page):
    """Create a new profile via the UI, set every field, save, and verify via API."""
    page.goto("/")

    # Open settings
    page.get_by_role("button", name="Settings", exact=True).click()
    expect(page.get_by_text("Agent Profiles")).to_be_visible()

    # Click "+ New" to create a profile
    page.get_by_role("button", name="+ New").click()

    # Wait for the editor to load
    name_input = page.locator("input[placeholder='Profile name']")
    name_input.wait_for(state="visible")

    # --- Identity ---
    name_input.fill("")
    name_input.fill("Test Agent")
    page.locator("input[placeholder='Short description']").fill("A test profile created by e2e")

    # Pick an icon (first emoji in the grid)
    page.locator("[class*='iconPicker']").click()
    picked_icon = page.locator("[class*='emojiOption']").first.inner_text().strip()
    page.locator("[class*='emojiOption']").first.click()

    # --- Model (first available) ---
    model_select = page.locator("select").first
    model_options = model_select.locator("option").all()
    selected_model = model_options[1].get_attribute("value") if len(model_options) > 1 else ""
    if selected_model:
        model_select.select_option(selected_model)

    # --- System prompt ---
    page.locator("textarea[placeholder='System prompt...']").fill("You are a test agent.")

    # --- Skills (toggle first available) ---
    skill_buttons = page.locator("button[class*='chip']")
    first_skill = None
    if skill_buttons.count() > 0:
        first_skill = skill_buttons.first.inner_text().strip()
        skill_buttons.first.click()

    # --- Advanced settings (set every inference field) ---
    page.get_by_text("Advanced Settings").click()

    # Temperature (input[placeholder='auto'] #0)
    page.locator("input[placeholder='auto']").nth(0).fill("0.8")
    # Top K (#1)
    page.locator("input[placeholder='auto']").nth(1).fill("50")
    # Top P (#2)
    page.locator("input[placeholder='auto']").nth(2).fill("0.9")
    # Repeat Penalty (#3)
    page.locator("input[placeholder='auto']").nth(3).fill("1.2")
    # Context / num_ctx (#4)
    page.locator("input[placeholder='auto']").nth(4).fill("16000")
    # Max Output / num_predict
    page.locator("input[placeholder='unlimited']").nth(0).fill("4096")
    # Iterations / max_iterations
    page.locator("input[placeholder='unlimited']").nth(1).fill("25")
    # Thinking toggle — checkbox is visually hidden, click the label wrapper
    page.locator("[class*='toggleLabel']").click()

    # --- Save ---
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(500)

    # --- Verify via API (reads from disk, no cache) ---
    profiles = page.request.get("/api/profiles").json()
    created = next((p for p in profiles if p["name"] == "Test Agent"), None)
    assert created is not None, f"Profile 'Test Agent' not found in {[p['name'] for p in profiles]}"

    # Identity
    assert created["name"] == "Test Agent"
    assert created["description"] == "A test profile created by e2e"
    assert created["icon"] == picked_icon

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
