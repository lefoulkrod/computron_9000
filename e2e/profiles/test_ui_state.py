"""E2E test: profile builder UI reflects saved profile state when loaded."""

import re

from playwright.sync_api import Page, expect


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
        page.goto("/")
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Agent Profiles").wait_for(state="visible")

        # Select the profile
        page.locator(f"[data-testid='profile-item-{profile_id}']").click()
        page.locator("input[placeholder='Profile name']").wait_for(state="visible")

        # --- Identity ---
        expect(page.locator("input[placeholder='Profile name']")).to_have_value("UI State Test")
        expect(page.locator("input[placeholder='Short description']")).to_have_value(
            "Verifies UI reflects saved state"
        )

        # --- Model ---
        if model_name:
            expect(page.locator("select").first).to_have_value(model_name)

        # --- System prompt ---
        expect(page.locator("textarea[placeholder='System prompt...']")).to_have_value(
            "You are a test agent for UI verification."
        )

        # --- Skills: coder and browser should be active ---
        skill_buttons = page.locator("button[class*='chip']")
        for i in range(skill_buttons.count()):
            btn = skill_buttons.nth(i)
            text = btn.inner_text().replace("✓", "").strip()
            if text in ("coder", "browser"):
                expect(btn).to_have_class(re.compile(r"chipActive"))
            else:
                expect(btn).not_to_have_class(re.compile(r"chipActive"))

        # --- Inference preset: "Code" should be active (temp=0.3, think=true) ---
        expect(
            page.locator("[class*='presetBtn']", has_text="Code")
        ).to_have_class(re.compile(r"presetActive"))

        # Other presets should NOT be active
        for label in ["Balanced", "Creative", "Precise"]:
            expect(
                page.locator("[class*='presetBtn']", has_text=label)
            ).not_to_have_class(re.compile(r"presetActive"))

        # --- Advanced settings ---
        page.get_by_text("Advanced Settings").click()

        # Temperature
        expect(page.locator("input[placeholder='auto']").nth(0)).to_have_value("0.3")
        # Top K — not set
        expect(page.locator("input[placeholder='auto']").nth(1)).to_have_value("")
        # Top P — not set
        expect(page.locator("input[placeholder='auto']").nth(2)).to_have_value("")
        # Repeat penalty — not set
        expect(page.locator("input[placeholder='auto']").nth(3)).to_have_value("")
        # Context (num_ctx)
        expect(page.locator("input[placeholder='auto']").nth(4)).to_have_value("32000")
        # Max output (num_predict)
        expect(page.locator("input[placeholder='unlimited']").nth(0)).to_have_value("2048")
        # Iterations (max_iterations)
        expect(page.locator("input[placeholder='unlimited']").nth(1)).to_have_value("10")
        # Thinking toggle
        expect(page.get_by_role("switch", name="Thinking")).to_be_checked()

    finally:
        page.request.delete(f"/api/profiles/{profile_id}")
