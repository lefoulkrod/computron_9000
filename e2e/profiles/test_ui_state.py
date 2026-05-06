"""E2E test: profile builder UI reflects saved profile state when loaded."""

import re

from playwright.sync_api import Page, expect

from e2e.pages import SettingsPage


def test_profile_ui_reflects_saved_state(page: Page):
    """Create a profile with specific settings via API, load it in the UI, verify all fields."""
    # Get the first available model to use
    models = page.request.get("/api/models").json().get("models", [])
    model_name = models[0]["name"] if models else ""

    # Create a profile with known values — use "code" preset (temperature=0.3, think=true)
    profile_id = "test_ui_state"
    page.request.post("/api/profiles", data={
        "id": profile_id,
        "name": "UI State Test",
        "description": "Verifies UI reflects saved state",
        "model": model_name,
        "system_prompt": "You are a test agent for UI verification.",
        "skills": ["coder", "browser"],
        "temperature": 0.3,
        "top_k": None,
        "top_p": None,
        "repeat_penalty": None,
        "think": True,
        "num_ctx": 32000,
        "num_predict": 2048,
        "max_iterations": 10,
    })

    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        builder = settings.builder

        # --- Identity ---
        expect(builder.name_input).to_have_value("UI State Test")
        expect(builder.description_input).to_have_value("Verifies UI reflects saved state")

        # --- Model ---
        if model_name:
            expect(builder.model_select).to_have_value(model_name)

        # --- System prompt ---
        expect(builder.system_prompt).to_have_value("You are a test agent for UI verification.")

        # --- Skills: coder and browser should be active ---
        for i in range(builder.skill_chips.count()):
            btn = builder.skill_chips.nth(i)
            text = btn.inner_text().replace("✓", "").strip()
            if text in ("coder", "browser"):
                expect(btn).to_have_class(re.compile(r"chipActive"))
            else:
                expect(btn).not_to_have_class(re.compile(r"chipActive"))

        # --- Inference preset: "Code" should be active (temp=0.3, think=true) ---
        expect(builder.preset("Code")).to_have_class(re.compile(r"presetActive"))

        # Other presets should NOT be active
        for label in ["Balanced", "Creative", "Precise"]:
            expect(builder.preset(label)).not_to_have_class(re.compile(r"presetActive"))

        # --- Advanced settings ---
        builder.open_advanced()

        expect(builder.field("temperature")).to_have_value("0.3")
        expect(builder.field("top_k")).to_have_value("")
        expect(builder.field("top_p")).to_have_value("")
        expect(builder.field("repeat_penalty")).to_have_value("")
        expect(builder.field("num_ctx")).to_have_value("32000")
        expect(builder.field("num_predict")).to_have_value("2048")
        expect(builder.field("max_iterations")).to_have_value("10")
        expect(builder.thinking_switch).to_be_checked()

    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
