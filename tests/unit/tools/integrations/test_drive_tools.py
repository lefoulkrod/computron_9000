"""Unit tests for the unified Drive agent tools.

Each tool wraps exactly one ``broker_client.call`` and shapes the result into
a plain-text string. The broker is stubbed; behavior is identical regardless
of which backend serves the verb.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.drive._format import format_entry, human_bytes
from tools.integrations.drive.delete import drive_delete
from tools.integrations.drive.download import drive_download
from tools.integrations.drive.list import drive_list
from tools.integrations.drive.mkdir import drive_mkdir
from tools.integrations.drive.move import drive_move
from tools.integrations.drive.share import drive_share
from tools.integrations.drive.upload import drive_upload


def _patch_call(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: Any = None,
    exc: Exception | None = None,
) -> list[tuple[str, str, dict]]:
    """Replace ``broker_client.call``; return a list that records each call."""
    log: list[tuple[str, str, dict]] = []

    async def _fake(integration_id: str, verb: str, args: dict, *, app_sock_path: Any) -> Any:
        log.append((integration_id, verb, args))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)
    return log


# --- format helpers --------------------------------------------------------

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


def test_format_entry_file_includes_handle_and_size() -> None:
    line = format_entry({
        "name": "report.pdf", "handle": "id:1AB", "is_dir": False,
        "size": 2048, "mime_type": "application/pdf",
    })
    assert "report.pdf" in line and "[id:1AB]" in line and "2 KB" in line


def test_format_entry_folder_marks_dir() -> None:
    line = format_entry({"name": "Docs", "handle": "Docs", "is_dir": True})
    assert "[dir]" in line and "Docs/" in line and "[Docs]" in line


# --- drive_list ------------------------------------------------------------

async def test_list_renders_entries_with_handles(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"entries": [
        {"name": "report.pdf", "handle": "id:1", "is_dir": False, "size": 2048, "mime_type": "application/pdf"},
        {"name": "Folder", "handle": "id:2", "is_dir": True, "size": 0},
    ]})
    out = await drive_list("gw_personal")
    assert "report.pdf" in out and "[id:1]" in out
    assert "Folder/" in out and "[id:2]" in out


async def test_list_empty_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"entries": []})
    assert "empty" in await drive_list("gw_personal")


async def test_list_with_pattern_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entries": []})
    out = await drive_list("gw_personal", pattern="report")
    assert "No matching" in out
    assert log[0][2]["pattern"] == "report"


async def test_list_passes_handle_to_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entries": []})
    await drive_list("icloud_drive_me", handle="Documents")
    assert log[0][2]["handle"] == "Documents"


async def test_list_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("x"))
    assert "not connected" in await drive_list("gw_personal")


# --- drive_download --------------------------------------------------------

async def test_download_confirms_with_local_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "local_path": "/downloads/report.pdf", "filename": "report.pdf",
        "mime_type": "application/pdf", "size": 2048,
    })
    out = await drive_download("gw_personal", "id:1AB")
    assert "report.pdf" in out and "/downloads/report.pdf" in out and "2 KB" in out


async def test_download_error_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("boom"))
    assert "boom" in await drive_download("gw_personal", "id:1AB")


# --- drive_upload ----------------------------------------------------------

async def test_upload_sends_base64_and_guesses_mime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"hello world")
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:NEW", "name": "notes.txt"}})
    out = await drive_upload("gw_personal", str(source))
    assert "notes.txt" in out and "id:NEW" in out
    sent = log[0][2]
    assert sent["name"] == "notes.txt"
    assert sent["mime_type"] == "text/plain"
    assert base64.b64decode(sent["data_b64"]) == b"hello world"
    assert sent["parent_handle"] == ""


async def test_upload_custom_name_and_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    source = tmp_path / "x.bin"
    source.write_bytes(b"\x00\x01")
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:NEW", "name": "renamed.bin"}})
    await drive_upload("gw_personal", str(source), parent_handle="id:FOLD", name="renamed.bin")
    sent = log[0][2]
    assert sent["name"] == "renamed.bin"
    assert sent["parent_handle"] == "id:FOLD"


async def test_upload_missing_local_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = _patch_call(monkeypatch, result={})
    out = await drive_upload("gw_personal", str(tmp_path / "nope.txt"))
    assert "not found" in out
    assert log == []


async def test_upload_permission_denied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "x.txt"
    source.write_bytes(b"x")
    _patch_call(monkeypatch, exc=broker_client.IntegrationPermissionDenied("denied"))
    assert "disabled" in await drive_upload("gw_personal", str(source))


# --- drive_mkdir -----------------------------------------------------------

async def test_mkdir_confirms_with_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:NEW", "name": "New"}})
    out = await drive_mkdir("gw_personal", "New")
    assert "New" in out and "id:NEW" in out
    assert log[0][2] == {"parent_handle": "", "name": "New"}


async def test_mkdir_under_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:NEW"}})
    await drive_mkdir("gw_personal", "Sub", parent_handle="id:PARENT")
    assert log[0][2]["parent_handle"] == "id:PARENT"


async def test_mkdir_permission_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationPermissionDenied("x"))
    assert "disabled" in await drive_mkdir("gw_personal", "Sub")


# --- drive_move ------------------------------------------------------------

async def test_move_reparents(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:M", "name": "a.txt"}})
    out = await drive_move("gw_personal", "id:F", dest_parent_handle="id:DEST")
    assert "id:M" in out
    sent = log[0][2]
    assert sent["handle"] == "id:F"
    assert sent["dest_parent_handle"] == "id:DEST"


async def test_move_renames_only(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"entry": {"handle": "id:M", "name": "b.txt"}})
    await drive_move("gw_personal", "id:F", name="b.txt")
    sent = log[0][2]
    assert sent["name"] == "b.txt"


async def test_move_rejects_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={})
    out = await drive_move("gw_personal", "id:F")
    assert "needs either" in out.lower()
    assert log == []


# --- drive_delete ----------------------------------------------------------

async def test_delete_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"deleted": True})
    out = await drive_delete("gw_personal", "id:F")
    assert "Deleted" in out


async def test_delete_permission_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationPermissionDenied("x"))
    assert "disabled" in await drive_delete("gw_personal", "id:F")


# --- drive_share -----------------------------------------------------------

async def test_share_grants_role(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={"permission": {"id": "p1"}})
    out = await drive_share("gw_personal", "id:F", "a@b.com", role="writer")
    assert "writer" in out and "a@b.com" in out
    sent = log[0][2]
    assert sent["email"] == "a@b.com" and sent["role"] == "writer" and sent["type"] == "user"


async def test_share_rejects_invalid_role(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _patch_call(monkeypatch, result={})
    out = await drive_share("gw_personal", "id:F", "a@b.com", role="owner")
    assert "role must be" in out
    assert log == []
