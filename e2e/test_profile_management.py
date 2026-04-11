"""E2E tests for agent profile management — edit, duplicate, delete."""

from playwright.sync_api import Page


def _open_settings(page: Page):
    """Navigate to the settings page, Agent Profiles tab."""
    page.goto("/")
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("button", name="Agent Profiles").wait_for(state="visible")


def _create_profile(page: Page, name: str) -> str:
    """Create a profile via API and return its ID."""
    profile_id = f"test_{name.lower().replace(' ', '_')}"
    page.request.post("/api/profiles", data={
        "id": profile_id,
        "name": name,
        "description": "test profile",
        "icon": "🧪",
        "model": "",
        "skills": [],
    })
    return profile_id


def _delete_profile(page: Page, profile_id: str):
    """Delete a profile via API."""
    page.request.delete(f"/api/profiles/{profile_id}")


def _select_profile_in_list(page: Page, profile_id: str):
    """Click a profile in the left-hand profile list by test ID."""
    page.locator(f"[data-testid='profile-item-{profile_id}']").click()
    page.locator("input[placeholder='Profile name']").wait_for(state="visible")


def test_edit_profile_persists(page: Page):
    """Edit an existing profile's name and description, verify changes saved."""
    profile_id = _create_profile(page, "Edit Target")
    try:
        _open_settings(page)
        _select_profile_in_list(page, profile_id)

        name_input = page.locator("input[placeholder='Profile name']")
        name_input.fill("Edited Agent")
        page.locator("input[placeholder='Short description']").fill("Updated description")

        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(500)

        profile = page.request.get(f"/api/profiles/{profile_id}").json()
        assert profile["name"] == "Edited Agent"
        assert profile["description"] == "Updated description"
    finally:
        _delete_profile(page, profile_id)


def test_duplicate_profile(page: Page):
    """Duplicate a profile and verify the copy exists with correct values."""
    profile_id = _create_profile(page, "Dup Source")
    try:
        _open_settings(page)
        _select_profile_in_list(page, profile_id)

        page.get_by_role("button", name="Duplicate").click()
        page.wait_for_timeout(500)

        profiles = page.request.get("/api/profiles").json()
        copies = [p for p in profiles if "Dup Source" in p["name"] and p["id"] != profile_id]
        assert len(copies) == 1, f"Expected 1 copy, got {len(copies)}"
        assert copies[0]["icon"] == "🧪"

        _delete_profile(page, copies[0]["id"])
    finally:
        _delete_profile(page, profile_id)


def test_delete_profile(page: Page):
    """Delete a profile via the UI and verify it's gone."""
    profile_id = _create_profile(page, "Delete Me")
    _open_settings(page)
    _select_profile_in_list(page, profile_id)

    page.get_by_role("button", name="Delete", exact=True).click()
    page.wait_for_timeout(500)

    profiles = page.request.get("/api/profiles").json()
    assert not any(p["id"] == profile_id for p in profiles)
