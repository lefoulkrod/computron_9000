"""Unit tests for the iCloud Drive (rclone-backed) agent tools.

Each tool wraps exactly one ``broker_client.call`` and shapes the result into
a plain-text string. These stub ``broker_client.call`` and assert on the
returned string — no rclone, no supervisor, no UDS.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes, split_remote_arg
from tools.integrations.icloud_drive.about import icloud_drive_about
from tools.integrations.icloud_drive.delete import icloud_drive_delete
from tools.integrations.icloud_drive.download import icloud_drive_download
from tools.integrations.icloud_drive.list_directory import icloud_drive_list_directory
from tools.integrations.icloud_drive.mkdir import icloud_drive_mkdir
from tools.integrations.icloud_drive.move import icloud_drive_move
from tools.integrations.icloud_drive.read_file import icloud_drive_read_file
from tools.integrations.icloud_drive.search import icloud_drive_search
from tools.integrations.icloud_drive.size import icloud_drive_size
from tools.integrations.icloud_drive.upload import icloud_drive_upload


def _patch_call(
    monkeypatch: pytest.MonkeyPatch, *, result: Any = None, exc: Exception | None = None,
) -> list[tuple[str, str, dict]]:
    """Replace ``broker_client.call`` with an async stub; return a call log."""
    log: list[tuple[str, str, dict]] = []

    async def _fake(integration_id: str, verb: str, args: dict, *, app_sock_path: Any) -> Any:
        log.append((integration_id, verb, args))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)
    return log


# --- format helpers ---------------------------------------------------------

@pytest.mark.parametrize(("n", "expected"), [
    (0, "0 B"),
    (-5, "0 B"),
    (512, "512 B"),
    (2048, "2 KB"),
    (1536, "1.5 KB"),
    (5 * 1024 * 1024, "5 MB"),
])
def test_human_bytes(n: int, expected: str) -> None:
    assert human_bytes(n) == expected


@pytest.mark.parametrize(("value", "expected"), [
    ("remote:Docs/a.txt", (True, "Docs/a.txt")),
    ("remote:/Docs/a.txt", (True, "Docs/a.txt")),
    ("remote/Docs/a.txt", (True, "Docs/a.txt")),
    ("/home/computron/a.txt", (False, "/home/computron/a.txt")),
    ("a.txt", (False, "a.txt")),
])
def test_split_remote_arg(value: str, expected: tuple[bool, str]) -> None:
    assert split_remote_arg(value) == expected


# --- read tools -------------------------------------------------------------

async def test_list_directory_formats_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"items": [
        {"name": "report.pdf", "size": 2048, "is_dir": False, "mod_time": ""},
        {"name": "Photos", "size": 0, "is_dir": True, "mod_time": ""},
    ]})
    out = await icloud_drive_list_directory("icloud_drive_me", "Documents")
    assert "report.pdf" in out and "(2 KB)" in out
    assert "Photos/" in out


async def test_list_directory_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"items": []})
    assert "empty" in await icloud_drive_list_directory("icloud_drive_me", "Documents")


async def test_list_directory_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    assert "not connected" in await icloud_drive_list_directory("icloud_drive_me")


async def test_about(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"total_bytes": 5 * 1024**3, "used_bytes": 1024**3, "free_bytes": 4 * 1024**3})
    out = await icloud_drive_about("icloud_drive_me")
    assert "5 GB" in out and "1 GB" in out and "4 GB" in out


async def test_search_with_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"matches": ["a/x.txt", "b/y.txt"], "count": 2})
    out = await icloud_drive_search("icloud_drive_me", "*.txt")
    assert "2 match" in out and "a/x.txt" in out


async def test_search_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"matches": [], "count": 0})
    assert "No files matching" in await icloud_drive_search("icloud_drive_me", "*.txt")


async def test_size(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"count": 3, "bytes": 2048})
    out = await icloud_drive_size("icloud_drive_me", "Documents")
    assert "3 file" in out and "2 KB" in out


async def test_read_file_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "content": base64.b64encode(b"hello\nworld").decode(), "encoding": "base64",
        "truncated": False, "size": 11,
    })
    assert await icloud_drive_read_file("icloud_drive_me", "notes.txt") == "hello\nworld"


async def test_read_file_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "content": base64.b64encode(b"abc").decode(), "encoding": "base64",
        "truncated": True, "size": 99,
    })
    out = await icloud_drive_read_file("icloud_drive_me", "big.txt", max_bytes=3)
    assert out.startswith("abc") and "truncated" in out


async def test_read_file_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "content": base64.b64encode(bytes([0x00, 0xFF])).decode(), "encoding": "base64",
        "truncated": False, "size": 2,
    })
    assert "binary file" in await icloud_drive_read_file("icloud_drive_me", "x.bin")


async def test_download_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"local_path": "/downloads/report.pdf", "bytes_copied": 2048})
    out = await icloud_drive_download("icloud_drive_me", "a/report.pdf")
    assert "/downloads/report.pdf" in out and "2 KB" in out
    assert log[0][1] == "copy_from_remote"
    assert "local_path" not in log[0][2]


async def test_download_explicit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"local_path": "/home/computron/r.pdf", "bytes_copied": 10})
    await icloud_drive_download("icloud_drive_me", "a/r.pdf", "/home/computron/r.pdf")
    assert log[0][2]["local_path"] == "/home/computron/r.pdf"


# --- write tools ------------------------------------------------------------

async def test_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"remote_path": "Docs/up.txt", "bytes_copied": 14})
    out = await icloud_drive_upload("icloud_drive_me", "/home/computron/up.txt", "Docs/up.txt")
    assert "Docs/up.txt" in out and "14 B" in out
    assert log[0][1] == "copy_to_remote"


async def test_upload_permission_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationPermissionDenied("denied"))
    assert "disabled" in await icloud_drive_upload("icloud_drive_me", "/home/computron/x", "Docs/x")


async def test_move_to_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"remote_path": "Archive/x.txt", "bytes_moved": 5})
    out = await icloud_drive_move("icloud_drive_me", "/home/computron/x.txt", "remote:Archive/x.txt")
    assert "Archive/x.txt" in out
    assert log[0][1] == "move_to_remote"
    assert log[0][2] == {"local_path": "/home/computron/x.txt", "remote_path": "Archive/x.txt"}


async def test_move_from_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"local_path": "/downloads/x.txt", "bytes_moved": 5})
    out = await icloud_drive_move("icloud_drive_me", "remote:Inbox/x.txt", "/downloads/x.txt")
    assert "/downloads/x.txt" in out
    assert log[0][1] == "move_from_remote"
    assert log[0][2] == {"remote_path": "Inbox/x.txt", "local_path": "/downloads/x.txt"}


async def test_move_rejects_both_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={})
    out = await icloud_drive_move("icloud_drive_me", "remote:a", "remote:b")
    assert "exactly one" in out.lower()
    assert log == []  # never reached the broker


async def test_move_rejects_neither_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={})
    out = await icloud_drive_move("icloud_drive_me", "/a", "/b")
    assert "exactly one" in out.lower()
    assert log == []


async def test_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"deleted": True})
    assert "Deleted" in await icloud_drive_delete("icloud_drive_me", "junk.txt")
    assert log[0][1] == "delete"


async def test_delete_permission_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationPermissionDenied("denied"))
    assert "disabled" in await icloud_drive_delete("icloud_drive_me", "junk.txt")


async def test_mkdir(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"created": True})
    assert "Created directory" in await icloud_drive_mkdir("icloud_drive_me", "New/Folder")
    assert log[0][1] == "mkdir"


async def test_generic_error_surfaces_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("rclone error: boom"))
    out = await icloud_drive_size("icloud_drive_me", "x")
    assert "boom" in out
