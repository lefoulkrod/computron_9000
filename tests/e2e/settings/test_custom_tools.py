"""E2E tests for the Custom Tools tab inside Settings."""

import json
import textwrap

from playwright.sync_api import Page, expect

from tests.e2e._helpers import container_exec
from tests.e2e.pages import SettingsPage


def _seed_tools(tools: list[dict]) -> None:
    """Write a custom-tools registry.json into the container's home dir."""
    payload = json.dumps(tools)
    script = textwrap.dedent(f"""
        from pathlib import Path
        from config import load_config
        path = Path(load_config().settings.home_dir) / 'custom_tools' / 'registry.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text({payload!r}, encoding='utf-8')
    """)
    container_exec(script)


def _read_tools() -> list[dict]:
    """Read the custom-tools registry.json from inside the container."""
    script = textwrap.dedent("""
        from pathlib import Path
        from config import load_config
        path = Path(load_config().settings.home_dir) / 'custom_tools' / 'registry.json'
        if path.exists():
            print(path.read_text(encoding='utf-8'))
        else:
            print('[]')
    """)
    return json.loads(container_exec(script) or "[]")


def _tool(name: str, *, description: str = '', tool_type: str = 'program', language: str = 'bash') -> dict:
    """Build a minimal but valid CustomToolDefinition dict."""
    return {
        "id": f"id-{name}",
        "name": name,
        "description": description,
        "type": tool_type,
        "language": language,
        "command_template": "",
        "script_filename": None,
        "parameters": [],
        "dependencies": [],
        "tags": [],
        "created_at": "2026-05-23T00:00:00+00:00",
        "updated_at": "2026-05-23T00:00:00+00:00",
    }


def _open_custom_tools(page: Page) -> SettingsPage:
    """Navigate to Settings → Custom Tools."""
    settings = SettingsPage(page).goto()
    page.get_by_role("button", name="Custom Tools").click()
    page.get_by_test_id("custom-tools-tab").wait_for(state="visible")
    return settings


def test_renders_seeded_tools(page: Page):
    """The Custom Tools tab lists one row per seeded tool with name + description."""
    _seed_tools([
        _tool("fetch_page", description="Fetch a URL and return text", tool_type="program", language="python"),
        _tool("ls_home", description="List the home dir", tool_type="command", language="bash"),
    ])

    _open_custom_tools(page)
    rows = page.get_by_test_id("custom-tools-row")
    expect(rows).to_have_count(2)
    expect(page.get_by_text("fetch_page")).to_be_visible()
    expect(page.get_by_text("Fetch a URL and return text")).to_be_visible()
    expect(page.get_by_text("ls_home")).to_be_visible()


def test_badge_label_reflects_type_or_language(page: Page):
    """Command type renders 'cmd'; otherwise the language is the badge label."""
    _seed_tools([
        _tool("py_tool", tool_type="program", language="python"),
        _tool("bash_tool", tool_type="program", language="bash"),
        _tool("cmd_tool", tool_type="command", language="bash"),
    ])

    _open_custom_tools(page)
    expect(page.locator('[data-tool-name="py_tool"]')).to_contain_text("python")
    expect(page.locator('[data-tool-name="bash_tool"]')).to_contain_text("bash")
    # Command type wins over language
    expect(page.locator('[data-tool-name="cmd_tool"]')).to_contain_text("cmd")


def test_delete_removes_row_and_persists(page: Page):
    """Clicking delete removes the row and the entry from the backend registry."""
    _seed_tools([
        _tool("fetch_page", description="Fetch a URL"),
        _tool("ls_home", description="List home"),
    ])

    _open_custom_tools(page)
    expect(page.get_by_test_id("custom-tools-row")).to_have_count(2)

    page.locator('[data-tool-name="fetch_page"]').get_by_test_id("custom-tools-delete").click()
    expect(page.get_by_test_id("custom-tools-row")).to_have_count(1)
    expect(page.get_by_text("fetch_page")).not_to_be_visible()

    stored = _read_tools()
    names = {t["name"] for t in stored}
    assert "fetch_page" not in names
    assert "ls_home" in names


def test_empty_state(page: Page):
    """With no tools seeded, the empty state renders."""
    _seed_tools([])

    _open_custom_tools(page)
    expect(page.get_by_text("No custom tools defined.")).to_be_visible()
    expect(page.get_by_test_id("custom-tools-row")).to_have_count(0)
