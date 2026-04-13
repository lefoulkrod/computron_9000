"""E2E tests for the agent-profile disable feature.

Covers:
  1. A non-default profile can be disabled; it disappears from the chat
     dropdown and /api/profiles (but stays in /api/profiles?include_disabled=true).
  2. Trying to disable the currently-set default_agent shows an inline
     error and leaves the server-side state unchanged.
  3. Disabled profiles render a 'disabled' badge in the profile list.
  4. Re-enabling a disabled profile restores it everywhere.
"""

from playwright.sync_api import Page, expect


def _open_settings(page: Page):
    page.goto("/")
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("button", name="Agent Profiles").wait_for(state="visible")


def _create_profile_via_api(page: Page, profile_id: str, name: str) -> None:
    """Create a profile via API and confirm 201."""
    resp = page.request.post("/api/profiles", data={
        "id": profile_id,
        "name": name,
        "description": "e2e disable test",
        "model": "",
        "enabled": True,
    })
    assert resp.status == 201, f"Failed to create profile: {resp.status}"


def _delete_profile_via_api(page: Page, profile_id: str) -> None:
    page.request.delete(f"/api/profiles/{profile_id}")


def test_disable_profile_hides_from_chat_dropdown(page: Page):
    """Disabling a non-default profile removes it from the chat selector."""
    profile_id = "e2e_disable_target"
    _create_profile_via_api(page, profile_id, "Disable Me")

    try:
        _open_settings(page)
        page.locator(f"[data-testid='profile-item-{profile_id}']").click()
        page.locator("input[placeholder='Profile name']").wait_for(state="visible")

        # Flip the enabled toggle off
        toggle = page.locator("[data-testid='profile-enabled-toggle'] input[type='checkbox']")
        expect(toggle).to_be_checked()
        toggle.uncheck()

        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(500)

        # API: enabled-only list should NOT include it
        enabled_only = page.request.get("/api/profiles").json()
        assert not any(p["id"] == profile_id for p in enabled_only), (
            f"Profile '{profile_id}' still appears in /api/profiles after being disabled"
        )

        # API: include_disabled=true SHOULD include it
        all_profiles = page.request.get("/api/profiles?include_disabled=true").json()
        match = next((p for p in all_profiles if p["id"] == profile_id), None)
        assert match is not None, "Disabled profile missing from include_disabled list"
        assert match["enabled"] is False

        # Chat panel dropdown: the option should not be present
        page.get_by_role("button", name="Settings", exact=True).click()  # close settings
        chat_selector = page.get_by_label("Agent profile")
        expect(chat_selector).to_be_visible()
        option = chat_selector.locator("option", has_text="Disable Me")
        expect(option).to_have_count(0)
    finally:
        _delete_profile_via_api(page, profile_id)


def test_disable_default_profile_shows_inline_error(page: Page):
    """Attempting to disable the currently-set default_agent is blocked."""
    # Read current default so we can target it precisely
    settings = page.request.get("/api/settings").json()
    default_id = settings.get("default_agent", "computron")

    _open_settings(page)
    page.locator(f"[data-testid='profile-item-{default_id}']").click()
    page.locator("input[placeholder='Profile name']").wait_for(state="visible")

    toggle = page.locator("[data-testid='profile-enabled-toggle'] input[type='checkbox']")
    expect(toggle).to_be_checked()
    toggle.uncheck()
    page.get_by_role("button", name="Save").click()

    # Inline error appears
    error = page.locator("[data-testid='profile-save-error']")
    expect(error).to_be_visible()
    expect(error).to_contain_text("default")

    # Toggle should revert to checked
    expect(toggle).to_be_checked()

    # API confirms no change
    profile = page.request.get(f"/api/profiles/{default_id}").json()
    assert profile["enabled"] is True


def test_disabled_badge_visible_in_profile_list(page: Page):
    """Profiles with enabled=false render a 'disabled' badge."""
    profile_id = "e2e_badge_target"
    _create_profile_via_api(page, profile_id, "Badge Target")
    # Flip it disabled directly via API
    page.request.put(f"/api/profiles/{profile_id}", data={
        "id": profile_id,
        "name": "Badge Target",
        "description": "e2e disable test",
        "model": "",
        "enabled": False,
    })

    try:
        _open_settings(page)
        item = page.locator(f"[data-testid='profile-item-{profile_id}']")
        expect(item).to_be_visible()
        # The disabled badge is a child span with the badgeDisabled class
        badge = item.locator("span[class*='badgeDisabled']")
        expect(badge).to_be_visible()
        expect(badge).to_contain_text("disabled")
    finally:
        _delete_profile_via_api(page, profile_id)


def test_reenable_profile_restores_it(page: Page):
    """Re-enabling a disabled profile brings it back in the enabled-only list."""
    profile_id = "e2e_reenable_target"
    _create_profile_via_api(page, profile_id, "Reenable Me")
    page.request.put(f"/api/profiles/{profile_id}", data={
        "id": profile_id,
        "name": "Reenable Me",
        "description": "",
        "model": "",
        "enabled": False,
    })

    try:
        _open_settings(page)
        page.locator(f"[data-testid='profile-item-{profile_id}']").click()
        page.locator("input[placeholder='Profile name']").wait_for(state="visible")

        toggle = page.locator("[data-testid='profile-enabled-toggle'] input[type='checkbox']")
        expect(toggle).not_to_be_checked()
        toggle.check()
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(500)

        # Enabled-only list now includes it
        enabled = page.request.get("/api/profiles").json()
        assert any(p["id"] == profile_id for p in enabled)
    finally:
        _delete_profile_via_api(page, profile_id)
