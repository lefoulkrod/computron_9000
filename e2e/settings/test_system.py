"""E2E tests for system settings page."""

from playwright.sync_api import Page

from e2e.pages import SettingsPage


def test_change_default_agent(page: Page):
    """Change the default agent and verify it persists."""
    settings = SettingsPage(page).goto_system()

    select = settings.system.default_agent_select
    options = select.locator("option").all()
    assert len(options) >= 2, "Need at least 2 profiles to test switching"

    current = select.input_value()
    new_value = next(o.get_attribute("value") for o in options if o.get_attribute("value") != current)
    select.select_option(new_value)
    page.wait_for_timeout(500)

    server_settings = page.request.get("/api/settings").json()
    assert server_settings["default_agent"] == new_value

    # Restore
    select.select_option(current)
    page.wait_for_timeout(500)


def test_change_vision_model(page: Page):
    """Change the vision model and verify it persists."""
    settings = SettingsPage(page).goto_system()

    select = settings.system.vision_model_select
    options = select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 vision model"

    original = select.input_value()
    new_model = options[1].get_attribute("value")
    select.select_option(new_model)
    page.wait_for_timeout(500)

    server_settings = page.request.get("/api/settings").json()
    assert server_settings["vision_model"] == new_model

    # Restore
    if original:
        select.select_option(original)
        page.wait_for_timeout(500)


def test_change_compaction_model(page: Page):
    """Change the compaction model and verify it persists."""
    settings = SettingsPage(page).goto_system()

    select = settings.system.compaction_model_select
    options = select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 model for compaction"

    original = select.input_value()
    new_model = options[1].get_attribute("value")
    select.select_option(new_model)
    page.wait_for_timeout(500)

    server_settings = page.request.get("/api/settings").json()
    assert server_settings["compaction_model"] == new_model

    # Restore
    if original:
        select.select_option(original)
        page.wait_for_timeout(500)


def test_vision_advanced_defaults_load(page: Page):
    """Advanced inference panel shows the migrated defaults on first open."""
    settings = SettingsPage(page).goto_system()

    server_settings = page.request.get("/api/settings").json()
    assert "vision_think" in server_settings, "vision_think missing — migration 003 did not run"
    assert "vision_options" in server_settings, "vision_options missing — migration 003 did not run"

    settings.system.open_vision_advanced()

    opts = server_settings["vision_options"]
    for key, expected in opts.items():
        field = settings.system.vision_option(key)
        assert field.input_value() == str(expected), (
            f"Field {key} showed {field.input_value()!r}, expected {expected!r}"
        )


def test_change_vision_advanced_settings(page: Page):
    """Every advanced field (Thinking + all four options) persists."""
    settings = SettingsPage(page).goto_system()

    original = page.request.get("/api/settings").json()
    original_think = bool(original.get("vision_think"))
    original_opts = dict(original["vision_options"])

    # Pick a new value for each numeric option that's guaranteed different.
    new_values = {
        "temperature": 0.9 if original_opts.get("temperature") != 0.9 else 0.1,
        "top_k": 99 if original_opts.get("top_k") != 99 else 42,
        "num_ctx": 12345 if original_opts.get("num_ctx") != 12345 else 16384,
        "num_predict": 777 if original_opts.get("num_predict") != 777 else 256,
    }

    settings.system.open_vision_advanced()

    # Toggle thinking.
    settings.system.vision_think_toggle.click()
    page.wait_for_timeout(300)

    # Change every option.
    for key, value in new_values.items():
        field = settings.system.vision_option(key)
        field.fill(str(value))
        field.blur()
        page.wait_for_timeout(300)

    saved = page.request.get("/api/settings").json()
    assert saved["vision_think"] == (not original_think), "vision_think did not persist"
    for key, expected in new_values.items():
        actual = saved["vision_options"][key]
        assert actual == expected, f"{key} did not persist: got {actual!r}, expected {expected!r}"

    # Restore.
    settings.system.vision_think_toggle.click()
    page.wait_for_timeout(200)
    for key, value in original_opts.items():
        field = settings.system.vision_option(key)
        field.fill(str(value))
        field.blur()
        page.wait_for_timeout(200)
