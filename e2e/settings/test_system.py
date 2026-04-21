"""E2E tests for system settings page."""

from playwright.sync_api import Page


def _open_system_settings(page: Page):
    """Navigate to Settings > System tab."""
    page.goto("/")
    page.locator("button[title='Settings']").click()
    page.get_by_role("button", name="System").click()
    # Wait for the system settings to load (Ollama connection status appears)
    page.locator("[class*='settingRow']").first.wait_for(state="visible")


def test_change_default_agent(page: Page):
    """Change the default agent and verify it persists."""
    _open_system_settings(page)

    # Default agent is the first select
    default_select = page.locator("select").first
    options = default_select.locator("option").all()
    assert len(options) >= 2, "Need at least 2 profiles to test switching"

    current = default_select.input_value()
    new_value = next(o.get_attribute("value") for o in options if o.get_attribute("value") != current)
    default_select.select_option(new_value)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["default_agent"] == new_value

    # Restore
    default_select.select_option(current)
    page.wait_for_timeout(500)


def test_change_vision_model(page: Page):
    """Change the vision model and verify it persists."""
    _open_system_settings(page)

    vision_select = page.locator("select").nth(1)
    options = vision_select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 vision model"

    original = vision_select.input_value()
    new_model = options[1].get_attribute("value")
    vision_select.select_option(new_model)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["vision_model"] == new_model

    # Restore
    if original:
        vision_select.select_option(original)
        page.wait_for_timeout(500)


def test_change_compaction_model(page: Page):
    """Change the compaction model and verify it persists."""
    _open_system_settings(page)

    compaction_select = page.locator("select").nth(2)
    options = compaction_select.locator("option").all()
    assert len(options) >= 2, "Need at least 1 model for compaction"

    original = compaction_select.input_value()
    new_model = options[1].get_attribute("value")
    compaction_select.select_option(new_model)
    page.wait_for_timeout(500)

    settings = page.request.get("/api/settings").json()
    assert settings["compaction_model"] == new_model

    # Restore
    if original:
        compaction_select.select_option(original)
        page.wait_for_timeout(500)


def test_vision_advanced_defaults_load(page: Page):
    """Advanced inference panel shows the migrated defaults on first open."""
    _open_system_settings(page)

    settings = page.request.get("/api/settings").json()
    assert "vision_think" in settings, "vision_think missing — migration 003 did not run"
    assert "vision_options" in settings, "vision_options missing — migration 003 did not run"

    # Expand the panel — it's collapsed by default.
    page.get_by_test_id("vision-advanced-toggle").click()
    page.get_by_test_id("vision-advanced-panel").wait_for(state="visible")

    opts = settings["vision_options"]
    for key, expected in opts.items():
        field = page.get_by_test_id(f"vision-option-{key}")
        assert field.input_value() == str(expected), (
            f"Field {key} showed {field.input_value()!r}, expected {expected!r}"
        )


def test_change_vision_advanced_settings(page: Page):
    """Every advanced field (Thinking + all four options) persists."""
    _open_system_settings(page)

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

    page.get_by_test_id("vision-advanced-toggle").click()
    page.get_by_test_id("vision-advanced-panel").wait_for(state="visible")

    # Toggle thinking.
    page.get_by_test_id("vision-think-toggle").click()
    page.wait_for_timeout(300)

    # Change every option.
    for key, value in new_values.items():
        field = page.get_by_test_id(f"vision-option-{key}")
        field.fill(str(value))
        field.blur()
        page.wait_for_timeout(300)

    saved = page.request.get("/api/settings").json()
    assert saved["vision_think"] == (not original_think), "vision_think did not persist"
    for key, expected in new_values.items():
        actual = saved["vision_options"][key]
        assert actual == expected, f"{key} did not persist: got {actual!r}, expected {expected!r}"

    # Restore.
    page.get_by_test_id("vision-think-toggle").click()
    page.wait_for_timeout(200)
    for key, value in original_opts.items():
        field = page.get_by_test_id(f"vision-option-{key}")
        field.fill(str(value))
        field.blur()
        page.wait_for_timeout(200)
