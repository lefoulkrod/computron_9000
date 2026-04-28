"""E2E tests for agent profile management — edit, duplicate, delete."""

from playwright.sync_api import Page

from e2e.pages import SettingsPage


def _create_profile(page: Page, name: str) -> str:
    """Create a profile via API and return its ID."""
    profile_id = f"test_{name.lower().replace(' ', '_')}"
    page.request.post("/api/profiles", data={
        "id": profile_id,
        "name": name,
        "description": "test profile",
        "model": "",
        "skills": [],
    })
    return profile_id


def _delete_profile(page: Page, profile_id: str):
    """Delete a profile via API."""
    page.request.delete(f"/api/profiles/{profile_id}")


def test_edit_profile_persists(page: Page):
    """Edit an existing profile's name and description, verify changes saved."""
    profile_id = _create_profile(page, "Edit Target")
    try:
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)

        settings.builder.name_input.fill("Edited Agent")
        settings.builder.description_input.fill("Updated description")
        settings.builder.save()
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
        settings = SettingsPage(page).goto()
        settings.profiles.select(profile_id)
        settings.builder.duplicate()
        page.wait_for_timeout(500)

        profiles = page.request.get("/api/profiles").json()
        copies = [p for p in profiles if "Dup Source" in p["name"] and p["id"] != profile_id]
        assert len(copies) == 1, f"Expected 1 copy, got {len(copies)}"

        _delete_profile(page, copies[0]["id"])
    finally:
        _delete_profile(page, profile_id)


def test_delete_profile(page: Page):
    """Delete a profile via the UI and verify it's gone."""
    profile_id = _create_profile(page, "Delete Me")
    settings = SettingsPage(page).goto()
    settings.profiles.select(profile_id)
    settings.builder.delete()
    page.wait_for_timeout(500)

    profiles = page.request.get("/api/profiles").json()
    assert not any(p["id"] == profile_id for p in profiles)
