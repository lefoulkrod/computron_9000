"""E2E tests for restoring preview-panel state when a conversation is reopened.

Seeds a conversation directly on disk (history + events + metadata) plus
the file the events reference in /home/computron, then loads it from the
recent-conversations list and asserts on what restores.

Covers four scenarios:
    1. File block appears inline in the chat (via _mergeFileOutputs).
    2. The preview tab the user had open re-opens automatically.
    3. The previously active tab is the one selected on restore.
    4. Tabs the user closed before leaving do NOT re-open.
"""

import json
import re
import time

import pytest
from playwright.sync_api import Page, expect

from tests.e2e._helpers import container_exec
from tests.e2e.pages import ChatView, PreviewPanel, RecentConversations

CONV_DIR = "/var/lib/computron/conversations"
VC_HOME = "/home/computron"


def _seed_conversation_with_files(
    conv_id: str,
    files: list[dict],
    *,
    title: str = "restored conv",
    preview_state: dict | None = None,
) -> None:
    """Seed a conversation + the files its events reference.

    Each ``files`` item: {"filename", "content_type", "content"} (utf-8 text).
    History gets one user + one assistant turn; events.json carries a
    file_output per file plus the bracketing root agent_started / completed.
    """
    history = [
        {"role": "user", "content": "make me some files"},
        {"role": "assistant", "content": "done"},
    ]
    events = [
        {"type": "agent_started", "agent_id": "root.computron.1",
         "agent_name": "COMPUTRON", "parent_agent_id": None,
         "instruction": "", "timestamp": "2026-05-20T12:00:00"},
    ]
    for f in files:
        events.append({
            "type": "file_output",
            "agent_id": "root.computron.1",
            "filename": f["filename"],
            "content_type": f["content_type"],
            "path": f"{VC_HOME}/{f['filename']}",
            "timestamp": "2026-05-20T12:00:01",
        })
    events.append({
        "type": "agent_completed", "agent_id": "root.computron.1",
        "agent_name": "COMPUTRON", "status": "success",
        "timestamp": "2026-05-20T12:00:02",
    })

    metadata: dict = {"title": title}
    if preview_state is not None:
        metadata["preview_state"] = preview_state

    history_json = json.dumps(history)
    events_json = json.dumps(events)
    metadata_json = json.dumps(metadata)
    file_payloads = json.dumps(files)

    script = (
        "import json, pathlib\n"
        f"d = pathlib.Path('{CONV_DIR}/{conv_id}')\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        f"(d / 'history.json').write_text({history_json!r})\n"
        f"(d / 'events.json').write_text({events_json!r})\n"
        f"(d / 'metadata.json').write_text({metadata_json!r})\n"
        f"home = pathlib.Path('{VC_HOME}')\n"
        f"for f in json.loads({file_payloads!r}):\n"
        "    (home / f['filename']).write_text(f['content'])\n"
        f"print('{conv_id}')\n"
    )
    container_exec(script)


def _delete_conversation(conv_id: str) -> None:
    container_exec(
        "import shutil, pathlib\n"
        f"p = pathlib.Path('{CONV_DIR}/{conv_id}')\n"
        "if p.exists(): shutil.rmtree(p)\n"
    )


def _delete_file(filename: str) -> None:
    container_exec(
        "import pathlib\n"
        f"p = pathlib.Path('{VC_HOME}/{filename}')\n"
        "if p.exists(): p.unlink()\n"
    )


@pytest.mark.e2e
def test_resume_renders_file_block_inline_in_chat(page: Page):
    """A file_output from a previous turn shows up as an inline FileOutput block."""
    nonce = time.time_ns()
    conv_id = f"e2e_restore_inline_{nonce}"
    filename = f"report_{nonce}.html"
    _seed_conversation_with_files(conv_id, [
        {"filename": filename, "content_type": "text/html",
         "content": "<html><body>seeded</body></html>"},
    ])

    try:
        ChatView(page).goto()
        RecentConversations(page).items.first.click()

        # The inline FileOutput block is identified by its Preview button.
        # Scope to the assistant message so we don't false-match a tab.
        assistant = page.get_by_test_id("message-assistant").last
        expect(assistant).to_be_visible(timeout=5_000)
        file_preview_btn = assistant.get_by_test_id("file-preview-btn").first
        expect(file_preview_btn).to_be_visible()
        expect(assistant).to_contain_text(filename)
    finally:
        _delete_conversation(conv_id)
        _delete_file(filename)


@pytest.mark.e2e
def test_resume_restores_open_file_tab(page: Page):
    """A file the user had previewed re-opens as a tab in the preview panel."""
    nonce = time.time_ns()
    conv_id = f"e2e_restore_tab_{nonce}"
    filename = f"open_{nonce}.html"
    _seed_conversation_with_files(
        conv_id,
        [{"filename": filename, "content_type": "text/html",
          "content": "<html><body>open me</body></html>"}],
        preview_state={
            "open_files": [filename],
            "active_tab": f"file:{filename}",
            "browser_visible": False,
            "terminal_visible": False,
            "desktop_visible": False,
            "generation_visible": False,
        },
    )

    try:
        ChatView(page).goto()
        RecentConversations(page).items.first.click()

        panel = PreviewPanel(page)
        expect(panel.file_tab(filename)).to_be_visible(timeout=5_000)
    finally:
        _delete_conversation(conv_id)
        _delete_file(filename)


@pytest.mark.e2e
def test_resume_restores_active_tab_selection(page: Page):
    """When multiple files were open, the previously-active tab is selected."""
    nonce = time.time_ns()
    conv_id = f"e2e_restore_active_{nonce}"
    file_a = f"a_{nonce}.html"
    file_b = f"b_{nonce}.html"
    _seed_conversation_with_files(
        conv_id,
        [
            {"filename": file_a, "content_type": "text/html",
             "content": "<html><body>a</body></html>"},
            {"filename": file_b, "content_type": "text/html",
             "content": "<html><body>b</body></html>"},
        ],
        preview_state={
            "open_files": [file_a, file_b],
            "active_tab": f"file:{file_b}",
            "browser_visible": False,
            "terminal_visible": False,
            "desktop_visible": False,
            "generation_visible": False,
        },
    )

    try:
        ChatView(page).goto()
        RecentConversations(page).items.first.click()

        panel = PreviewPanel(page)
        expect(panel.file_tab(file_a)).to_be_visible(timeout=5_000)
        expect(panel.file_tab(file_b)).to_be_visible()

        # PreviewPanel adds an "active" class to the selected tab button.
        # CSS-Modules hashes the class name; match on the substring.
        expect(panel.file_tab(file_b)).to_have_class(re.compile(r"tabActive"))
        expect(panel.file_tab(file_a)).not_to_have_class(re.compile(r"tabActive"))
    finally:
        _delete_conversation(conv_id)
        _delete_file(file_a)
        _delete_file(file_b)


@pytest.mark.e2e
def test_resume_does_not_reopen_closed_tabs(page: Page):
    """A file that's in the history but NOT in open_files stays closed on restore."""
    nonce = time.time_ns()
    conv_id = f"e2e_restore_closed_{nonce}"
    open_file = f"keep_{nonce}.html"
    closed_file = f"closed_{nonce}.html"
    _seed_conversation_with_files(
        conv_id,
        [
            {"filename": open_file, "content_type": "text/html",
             "content": "<html><body>keep</body></html>"},
            {"filename": closed_file, "content_type": "text/html",
             "content": "<html><body>closed</body></html>"},
        ],
        preview_state={
            # User had keep_file open, explicitly closed closed_file.
            "open_files": [open_file],
            "active_tab": f"file:{open_file}",
            "browser_visible": False,
            "terminal_visible": False,
            "desktop_visible": False,
            "generation_visible": False,
        },
    )

    try:
        ChatView(page).goto()
        RecentConversations(page).items.first.click()

        panel = PreviewPanel(page)
        expect(panel.file_tab(open_file)).to_be_visible(timeout=5_000)
        # Closed tab does NOT come back, even though the file is in events.
        expect(panel.file_tab(closed_file)).to_have_count(0)
    finally:
        _delete_conversation(conv_id)
        _delete_file(open_file)
        _delete_file(closed_file)
