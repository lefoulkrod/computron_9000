"""Tests for the canonical Drive verbs on the Google Workspace broker.

The verb dispatcher does handle resolution + permission gating + maps results
through the unified entry shape. Tests stub ``DriveClient`` so what's under
test is the dispatcher, not Drive API plumbing.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from integrations._rpc import RpcError
from integrations.brokers.google_workspace_broker._verbs import VerbDispatcher, _drive_entry
from integrations.permissions import Access, Capability


def _drive_scope_creds() -> Any:
    """Minimal Credentials stand-in — only the ``scopes`` attribute is read."""
    creds = MagicMock()
    creds.scopes = ["https://www.googleapis.com/auth/drive.file"]
    return creds


class _StubDriveClient:
    """Records calls; returns canned data. Stand-in for ``DriveClient``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        # Path-resolution table: path -> id (None means not found).
        self.paths: dict[str, str | None] = {"": "root"}
        # Default canned returns.
        self.list_files_return: list[dict[str, Any]] = []
        self.list_in_parent_matching_return: list[dict[str, Any]] = []
        self.export_file_return: tuple[bytes, str, str] = (b"hello", "f.txt", "text/plain")
        self.upload_file_return: dict[str, Any] = {"id": "u1", "name": "up.txt", "mimeType": "text/plain"}
        self.create_folder_return: dict[str, Any] = {"id": "fld1", "name": "New", "mimeType": "application/vnd.google-apps.folder"}
        self.move_file_return: dict[str, Any] = {"id": "m1", "name": "moved.txt", "mimeType": "text/plain"}
        self.share_file_return: dict[str, Any] = {"id": "perm1", "role": "reader", "type": "user", "emailAddress": "x@y.com"}

    def _record(self, name: str, *args: Any, **kw: Any) -> None:
        self.calls.append((name, args, kw))

    def resolve_path(self, path: str) -> str | None:
        self._record("resolve_path", path)
        return self.paths.get(path)

    def list_files(self, folder_id: str = "root", limit: int = 50) -> list[dict[str, Any]]:
        self._record("list_files", folder_id, limit)
        return self.list_files_return

    def list_in_parent_matching(
        self, parent_id: str, name_substring: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._record("list_in_parent_matching", parent_id, name_substring, limit)
        return self.list_in_parent_matching_return

    def export_file(self, file_id: str) -> tuple[bytes, str, str]:
        self._record("export_file", file_id)
        return self.export_file_return

    def upload_file(
        self, name: str, content: bytes, mime_type: str, parent_id: str | None = None,
    ) -> dict[str, Any]:
        self._record("upload_file", name, content, mime_type, parent_id)
        return self.upload_file_return

    def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        self._record("create_folder", name, parent_id)
        return self.create_folder_return

    def move_file(
        self, file_id: str, new_parent_id: str, new_name: str | None = None,
    ) -> dict[str, Any]:
        self._record("move_file", file_id, new_parent_id, new_name)
        return self.move_file_return

    def trash_file(self, file_id: str) -> dict[str, Any]:
        self._record("trash_file", file_id)
        return {"id": file_id, "trashed": True}

    def share_file(
        self, file_id: str, role: str, share_type: str, email: str | None = None,
    ) -> dict[str, Any]:
        self._record("share_file", file_id, role, share_type, email)
        return self.share_file_return


def _dispatcher(
    *,
    access: Access = Access.READ_WRITE,
    downloads_dir: Path | None = None,
    tmp_path: Path | None = None,
) -> tuple[VerbDispatcher, _StubDriveClient]:
    dir_path = downloads_dir or (tmp_path / "downloads" if tmp_path else Path("/tmp/gw-test"))
    d = VerbDispatcher(
        _drive_scope_creds(),
        permissions={Capability.DRIVE: access},
        downloads_dir=dir_path,
    )
    stub = _StubDriveClient()
    d._drive = stub
    return d, stub


# --- _drive_entry shape ----------------------------------------------------

def test_drive_entry_file() -> None:
    entry = _drive_entry({
        "id": "1AB", "name": "report.pdf",
        "mimeType": "application/pdf", "size": "12345",
        "modifiedTime": "2026-05-12T10:00:00Z",
    })
    assert entry == {
        "name": "report.pdf",
        "handle": "id:1AB",
        "is_dir": False,
        "size": 12345,
        "mime_type": "application/pdf",
        "modified": "2026-05-12T10:00:00Z",
    }


def test_drive_entry_folder() -> None:
    entry = _drive_entry({
        "id": "fld", "name": "Docs",
        "mimeType": "application/vnd.google-apps.folder",
        "modifiedTime": "",
    })
    assert entry["is_dir"] is True
    assert entry["size"] == 0
    assert entry["handle"] == "id:fld"


# --- _resolve_handle -------------------------------------------------------

async def test_resolve_handle_empty_is_root(tmp_path: Path) -> None:
    d, _ = _dispatcher(tmp_path=tmp_path)
    assert await d._resolve_handle("") == "root"


async def test_resolve_handle_id_prefix(tmp_path: Path) -> None:
    d, _ = _dispatcher(tmp_path=tmp_path)
    assert await d._resolve_handle("id:1XYZ") == "1XYZ"
    assert await d._resolve_handle("id:root") == "root"


async def test_resolve_handle_path_walks(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.paths["Documents/report.pdf"] = "1AB"
    assert await d._resolve_handle("Documents/report.pdf") == "1AB"


async def test_resolve_handle_missing_path_returns_none(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.paths["Missing/Stuff"] = None
    assert await d._resolve_handle("Missing/Stuff") is None


# --- drive_list ------------------------------------------------------------

async def test_drive_list_no_pattern_lists_children(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.list_files_return = [
        {"id": "1", "name": "report.pdf", "mimeType": "application/pdf", "size": "2048", "modifiedTime": ""},
        {"id": "2", "name": "Folder", "mimeType": "application/vnd.google-apps.folder", "modifiedTime": ""},
    ]
    result = await d.dispatch("drive_list", {})
    assert [e["name"] for e in result["entries"]] == ["report.pdf", "Folder"]
    assert result["entries"][0]["handle"] == "id:1"
    assert result["entries"][1]["is_dir"] is True
    assert ("list_files", ("root", 50), {}) in stub.calls


async def test_drive_list_with_pattern_uses_search(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.list_in_parent_matching_return = [
        {"id": "9", "name": "notes.md", "mimeType": "text/markdown", "size": "12", "modifiedTime": ""},
    ]
    result = await d.dispatch("drive_list", {"pattern": "notes"})
    assert result["entries"][0]["name"] == "notes.md"
    assert ("list_in_parent_matching", ("root", "notes", 50), {}) in stub.calls


async def test_drive_list_with_id_handle(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.list_files_return = []
    await d.dispatch("drive_list", {"handle": "id:1ABC"})
    assert ("list_files", ("1ABC", 50), {}) in stub.calls


async def test_drive_list_with_path_handle(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.paths["Documents"] = "fld1"
    stub.list_files_return = []
    await d.dispatch("drive_list", {"handle": "Documents"})
    assert ("list_files", ("fld1", 50), {}) in stub.calls


async def test_drive_list_path_not_found(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.paths["Missing"] = None
    with pytest.raises(RpcError, match="path not found"):
        await d.dispatch("drive_list", {"handle": "Missing"})


# --- drive_download --------------------------------------------------------

async def test_drive_download_writes_to_disk(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    stub.export_file_return = (b"hello world", "report.txt", "text/plain")
    result = await d.dispatch("drive_download", {"handle": "id:1XYZ"})
    assert result["filename"] == "report.txt"
    assert result["mime_type"] == "text/plain"
    assert result["size"] == 11
    written = Path(result["local_path"])
    assert written.read_bytes() == b"hello world"
    assert ("export_file", ("1XYZ",), {}) in stub.calls


async def test_drive_download_requires_handle(tmp_path: Path) -> None:
    d, _ = _dispatcher(tmp_path=tmp_path)
    with pytest.raises(RpcError, match="required"):
        await d.dispatch("drive_download", {})


# --- drive_upload ----------------------------------------------------------

async def test_drive_upload_decodes_b64_and_uploads(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    payload = b"file content"
    result = await d.dispatch("drive_upload", {
        "name": "up.txt",
        "data_b64": base64.b64encode(payload).decode(),
        "mime_type": "text/plain",
    })
    assert result["entry"]["name"] == "up.txt"
    call_name, args, _ = stub.calls[0]
    assert call_name == "upload_file"
    assert args == ("up.txt", payload, "text/plain", "root")


async def test_drive_upload_with_explicit_parent(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    await d.dispatch("drive_upload", {
        "name": "x", "data_b64": base64.b64encode(b"x").decode(),
        "mime_type": "text/plain", "parent_handle": "id:FOLD",
    })
    assert stub.calls[0][1][3] == "FOLD"


async def test_drive_upload_rejects_bad_base64(tmp_path: Path) -> None:
    d, _ = _dispatcher(tmp_path=tmp_path)
    with pytest.raises(RpcError, match="invalid base64"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": "not!!!base64!!!", "mime_type": "text/plain",
        })


async def test_drive_upload_denied_when_read_only(tmp_path: Path) -> None:
    d, _ = _dispatcher(access=Access.READ, tmp_path=tmp_path)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": base64.b64encode(b"x").decode(),
            "mime_type": "text/plain",
        })


# --- drive_mkdir -----------------------------------------------------------

async def test_drive_mkdir_creates_folder(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    result = await d.dispatch("drive_mkdir", {"name": "New", "parent_handle": "id:FOLD"})
    assert result["entry"]["name"] == "New"
    assert result["entry"]["is_dir"] is True
    assert ("create_folder", ("New", "FOLD"), {}) in stub.calls


# --- drive_move ------------------------------------------------------------

async def test_drive_move_reparents_and_renames(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    await d.dispatch("drive_move", {
        "handle": "id:F1", "dest_parent_handle": "id:DEST", "name": "renamed.txt",
    })
    assert ("move_file", ("F1", "DEST", "renamed.txt"), {}) in stub.calls


async def test_drive_move_keeps_name_when_omitted(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    await d.dispatch("drive_move", {"handle": "id:F1", "dest_parent_handle": "id:DEST"})
    assert ("move_file", ("F1", "DEST", None), {}) in stub.calls


# --- drive_delete ----------------------------------------------------------

async def test_drive_delete_trashes(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    result = await d.dispatch("drive_delete", {"handle": "id:F1"})
    assert result == {"deleted": True}
    assert ("trash_file", ("F1",), {}) in stub.calls


async def test_drive_delete_denied_when_read_only(tmp_path: Path) -> None:
    d, _ = _dispatcher(access=Access.READ, tmp_path=tmp_path)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_delete", {"handle": "id:F1"})


# --- drive_share -----------------------------------------------------------

async def test_drive_share_creates_permission(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    result = await d.dispatch("drive_share", {
        "handle": "id:F1", "role": "reader", "email": "a@b.com",
    })
    assert result["permission"]["role"] == "reader"
    assert ("share_file", ("F1", "reader", "user", "a@b.com"), {}) in stub.calls


async def test_drive_share_defaults_type_to_user(tmp_path: Path) -> None:
    d, stub = _dispatcher(tmp_path=tmp_path)
    await d.dispatch("drive_share", {"handle": "id:F1", "role": "writer", "email": "x@y.com"})
    assert stub.calls[0][1][2] == "user"
