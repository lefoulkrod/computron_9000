"""E2E tests for the Memory tab inside Settings."""

import json
import textwrap

from playwright.sync_api import Page, expect

from tests.e2e._helpers import container_exec
from tests.e2e.pages import SettingsPage


def _seed_memories(entries: dict) -> None:
    """Write a memory.json into the container's home dir."""
    payload = json.dumps({
        k: {"value": v["value"], "hidden": v.get("hidden", False)}
        for k, v in entries.items()
    })
    script = textwrap.dedent(f"""
        from pathlib import Path
        from config import load_config
        path = Path(load_config().settings.home_dir) / 'memory.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text({payload!r}, encoding='utf-8')
    """)
    container_exec(script)


def _read_memories() -> dict:
    """Read memory.json from inside the container."""
    script = textwrap.dedent("""
        from pathlib import Path
        from config import load_config
        path = Path(load_config().settings.home_dir) / 'memory.json'
        if path.exists():
            print(path.read_text(encoding='utf-8'))
        else:
            print('{}')
    """)
    return json.loads(container_exec(script) or "{}")


def test_renders_seeded_memories(page: Page):
    """Memory tab shows one row per seeded entry."""
    _seed_memories({
        "user_name": {"value": "Test User"},
        "user_email": {"value": "test@example.com"},
        "user_phone": {"value": "555-0100", "hidden": True},
    })

    SettingsPage(page).goto_memory()
    rows = page.get_by_test_id("memory-row")
    expect(rows).to_have_count(3)
    expect(page.get_by_text("user_name")).to_be_visible()
    expect(page.get_by_text("Test User")).to_be_visible()
    expect(page.get_by_text("test@example.com")).to_be_visible()
    # Hidden value is masked
    phone_row = page.locator('[data-key="user_phone"]')
    expect(phone_row.get_by_test_id("memory-value")).to_have_text("••••••••")


def test_toggle_hide_persists(page: Page):
    """Clicking the hide toggle masks the value and persists on the backend."""
    _seed_memories({"user_email": {"value": "test@example.com"}})

    SettingsPage(page).goto_memory()
    row = page.locator('[data-key="user_email"]')
    expect(row.get_by_test_id("memory-value")).to_have_text("test@example.com")

    row.get_by_test_id("memory-hide").click()
    expect(row.get_by_test_id("memory-value")).to_have_text("••••••••")

    stored = _read_memories()
    assert stored["user_email"]["hidden"] is True


def test_delete_removes_row_and_persists(page: Page):
    """Clicking delete removes the row and the entry from the backend."""
    _seed_memories({
        "user_name": {"value": "Test User"},
        "user_email": {"value": "test@example.com"},
    })

    SettingsPage(page).goto_memory()
    expect(page.get_by_test_id("memory-row")).to_have_count(2)

    page.locator('[data-key="user_name"]').get_by_test_id("memory-delete").click()
    expect(page.get_by_test_id("memory-row")).to_have_count(1)
    expect(page.get_by_text("user_name")).not_to_be_visible()

    stored = _read_memories()
    assert "user_name" not in stored
    assert "user_email" in stored


def test_empty_state(page: Page):
    """With no memories seeded, the empty state renders."""
    _seed_memories({})

    SettingsPage(page).goto_memory()
    expect(page.get_by_text("No memories yet.")).to_be_visible()
    expect(page.get_by_test_id("memory-row")).to_have_count(0)
