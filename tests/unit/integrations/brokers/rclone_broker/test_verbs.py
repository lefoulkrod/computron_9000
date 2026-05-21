"""Tests for ``brokers/rclone_broker/_verbs.py`` — the dispatcher logic only.

The dispatcher is pure routing: verb name -> rcd RC-API call -> response
dict, with a per-capability permission gate in the middle. ``RcdClient`` is
stubbed so the tests exercise the dispatcher's translation between agent
verb shapes and rclone's RC API without spawning rcd.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from integrations._rpc import RpcError
from integrations.brokers.rclone_broker._rcd import RcdAuthError, RcdError
from integrations.brokers.rclone_broker._verbs import (
    VerbDispatcher,
    _join_remote_path,
    _rcd_entry,
    _validate_remote_path,
)
from integrations.permissions import Access, Capability


class _StubRcdClient:
    """Records (endpoint, params) tuples. Returns canned responses by endpoint."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.uploads: list[dict[str, Any]] = []
        self.responses: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}

    async def call(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((endpoint, params or {}))
        if endpoint in self.errors:
            raise self.errors[endpoint]
        return self.responses.get(endpoint, {})

    async def upload_file(
        self, *, parent_path: str, filename: str, content: bytes, mime_type: str = "",
    ) -> None:
        self.uploads.append({
            "parent_path": parent_path,
            "filename": filename,
            "content": content,
            "mime_type": mime_type,
        })
        if "operations/uploadfile" in self.errors:
            raise self.errors["operations/uploadfile"]


def _dispatcher(
    *,
    access: Access = Access.READ_WRITE,
    tmp_path: Path | None = None,
) -> tuple[VerbDispatcher, _StubRcdClient]:
    perms = {Capability.DRIVE: access} if access != Access.OFF else {}
    rcd = _StubRcdClient()
    downloads = (tmp_path / "downloads") if tmp_path else Path("/tmp/rcd-test-downloads")
    return (
        VerbDispatcher(permissions=perms, rcd=rcd, downloads_dir=downloads),  # type: ignore[arg-type]
        rcd,
    )


# --- helpers ---------------------------------------------------------------

def test_remote_path_simple() -> None:
    assert _validate_remote_path("Documents/notes.txt") == "Documents/notes.txt"


def test_remote_path_root_empty() -> None:
    assert _validate_remote_path("") == ""


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/../b", ".."])
def test_remote_path_traversal_blocked(bad: str) -> None:
    with pytest.raises(RpcError, match="path traversal"):
        _validate_remote_path(bad)


def test_join_remote_path() -> None:
    assert _join_remote_path("", "a.txt") == "a.txt"
    assert _join_remote_path("Docs", "a.txt") == "Docs/a.txt"
    assert _join_remote_path("Docs/", "a.txt") == "Docs/a.txt"


def test_rcd_entry_file() -> None:
    entry = _rcd_entry(
        {"Name": "report.pdf", "Size": 2048, "IsDir": False, "ModTime": "2026-01-01T00:00:00Z"},
        parent_path="Documents",
    )
    assert entry == {
        "name": "report.pdf",
        "handle": "Documents/report.pdf",
        "is_dir": False,
        "size": 2048,
        "mime_type": "",
        "modified": "2026-01-01T00:00:00Z",
    }


def test_rcd_entry_root_parent() -> None:
    entry = _rcd_entry({"Name": "x", "IsDir": True}, parent_path="")
    assert entry["handle"] == "x"
    assert entry["is_dir"] is True


# --- permission gate ------------------------------------------------------

async def test_unknown_verb_raises() -> None:
    d, _ = _dispatcher()
    with pytest.raises(RpcError, match="unknown verb"):
        await d.dispatch("nope", {})


async def test_read_verb_denied_without_drive_access() -> None:
    d, _ = _dispatcher(access=Access.OFF)
    with pytest.raises(RpcError, match="PERMISSION_DENIED|requires drive"):
        await d.dispatch("drive_list", {})


async def test_write_verb_denied_when_read_only() -> None:
    d, _ = _dispatcher(access=Access.READ)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_delete", {"handle": "x.txt"})


async def test_read_verb_allowed_when_read_only() -> None:
    d, rcd = _dispatcher(access=Access.READ)
    rcd.responses["operations/list"] = {"list": []}
    assert "entries" in await d.dispatch("drive_list", {})


# --- drive_list ----------------------------------------------------------

async def test_drive_list_no_pattern_returns_entries() -> None:
    d, rcd = _dispatcher()
    rcd.responses["operations/list"] = {"list": [
        {"Name": "a.txt", "Size": 10, "IsDir": False, "ModTime": ""},
        {"Name": "Sub", "Size": 0, "IsDir": True, "ModTime": ""},
    ]}
    result = await d.dispatch("drive_list", {})
    assert [e["name"] for e in result["entries"]] == ["a.txt", "Sub"]
    assert result["entries"][1]["is_dir"] is True
    assert rcd.calls[0] == ("operations/list", {"fs": "default:", "remote": ""})


async def test_drive_list_scopes_to_handle() -> None:
    d, rcd = _dispatcher()
    rcd.responses["operations/list"] = {"list": [
        {"Name": "leaf.txt", "Size": 1, "IsDir": False, "ModTime": ""},
    ]}
    result = await d.dispatch("drive_list", {"handle": "Documents"})
    assert result["entries"][0]["handle"] == "Documents/leaf.txt"
    assert rcd.calls[0][1] == {"fs": "default:", "remote": "Documents"}


async def test_drive_list_pattern_filters_clientside() -> None:
    d, rcd = _dispatcher()
    rcd.responses["operations/list"] = {"list": [
        {"Name": "report.pdf"}, {"Name": "photo.jpg"}, {"Name": "report_v2.pdf"},
    ]}
    result = await d.dispatch("drive_list", {"pattern": "report"})
    names = [e["name"] for e in result["entries"]]
    assert names == ["report.pdf", "report_v2.pdf"]


async def test_drive_list_pattern_is_case_insensitive() -> None:
    d, rcd = _dispatcher()
    rcd.responses["operations/list"] = {"list": [
        {"Name": "REPORT.pdf"}, {"Name": "photo.jpg"},
    ]}
    result = await d.dispatch("drive_list", {"pattern": "report"})
    assert [e["name"] for e in result["entries"]] == ["REPORT.pdf"]


async def test_drive_list_traversal_blocked() -> None:
    d, _ = _dispatcher()
    with pytest.raises(RpcError, match="path traversal"):
        await d.dispatch("drive_list", {"handle": "../secret"})


# --- drive_download ------------------------------------------------------

async def test_drive_download_calls_copyfile_with_local_dst(tmp_path: Path) -> None:
    d, rcd = _dispatcher(tmp_path=tmp_path)
    downloads = tmp_path / "downloads"
    # Pretend rcd actually wrote the file.
    rcd.responses["operations/copyfile"] = {}

    async def fake_call(endpoint, params=None):
        rcd.calls.append((endpoint, params or {}))
        if endpoint == "operations/copyfile":
            downloads.mkdir(parents=True, exist_ok=True)
            (downloads / "report.pdf").write_bytes(b"hello world")
        return rcd.responses.get(endpoint, {})

    rcd.call = fake_call  # type: ignore[method-assign]
    result = await d.dispatch("drive_download", {"handle": "Docs/report.pdf"})
    assert result["filename"] == "report.pdf"
    assert result["size"] == 11
    assert Path(result["local_path"]).read_bytes() == b"hello world"
    # The dst path passed to rcd ends with a slash so rclone treats it as a fs root.
    copyfile_args = rcd.calls[0][1]
    assert copyfile_args["srcFs"] == "default:"
    assert copyfile_args["srcRemote"] == "Docs/report.pdf"
    assert copyfile_args["dstFs"].endswith("/")
    assert copyfile_args["dstRemote"] == "report.pdf"


async def test_drive_download_requires_handle() -> None:
    d, _ = _dispatcher()
    with pytest.raises(RpcError, match="required"):
        await d.dispatch("drive_download", {})


# --- drive_upload --------------------------------------------------------

async def test_drive_upload_decodes_b64_and_forwards() -> None:
    d, rcd = _dispatcher()
    payload = b"file content"
    result = await d.dispatch("drive_upload", {
        "name": "up.txt", "data_b64": base64.b64encode(payload).decode(),
        "parent_handle": "Docs", "mime_type": "text/plain",
    })
    assert result["entry"]["handle"] == "Docs/up.txt"
    assert result["entry"]["size"] == len(payload)
    assert rcd.uploads == [{
        "parent_path": "Docs",
        "filename": "up.txt",
        "content": payload,
        "mime_type": "text/plain",
    }]


async def test_drive_upload_rejects_bad_base64() -> None:
    d, _ = _dispatcher()
    with pytest.raises(RpcError, match="invalid base64"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": "not!!base64!!", "parent_handle": "",
        })


async def test_drive_upload_denied_when_read_only() -> None:
    d, _ = _dispatcher(access=Access.READ)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": base64.b64encode(b"x").decode(), "parent_handle": "",
        })


# --- drive_mkdir, drive_move, drive_delete -------------------------------

async def test_drive_mkdir() -> None:
    d, rcd = _dispatcher()
    result = await d.dispatch("drive_mkdir", {"parent_handle": "Docs", "name": "New"})
    assert result["entry"]["handle"] == "Docs/New"
    assert result["entry"]["is_dir"] is True
    assert rcd.calls[0] == ("operations/mkdir", {"fs": "default:", "remote": "Docs/New"})


async def test_drive_move_renames() -> None:
    d, rcd = _dispatcher()
    result = await d.dispatch("drive_move", {
        "handle": "Inbox/a.txt", "dest_parent_handle": "Archive", "name": "b.txt",
    })
    assert result["entry"]["handle"] == "Archive/b.txt"
    assert rcd.calls[0] == ("operations/movefile", {
        "srcFs": "default:", "srcRemote": "Inbox/a.txt",
        "dstFs": "default:", "dstRemote": "Archive/b.txt",
    })


async def test_drive_move_keeps_name_when_omitted() -> None:
    d, rcd = _dispatcher()
    result = await d.dispatch("drive_move", {
        "handle": "Inbox/a.txt", "dest_parent_handle": "Archive",
    })
    assert result["entry"]["name"] == "a.txt"
    assert result["entry"]["handle"] == "Archive/a.txt"
    assert rcd.calls[0][1]["dstRemote"] == "Archive/a.txt"


async def test_drive_delete_file() -> None:
    d, rcd = _dispatcher()
    rcd.responses["operations/deletefile"] = {}
    assert await d.dispatch("drive_delete", {"handle": "x.txt"}) == {"deleted": True}
    assert rcd.calls[0] == ("operations/deletefile", {"fs": "default:", "remote": "x.txt"})


async def test_drive_delete_falls_back_to_purge() -> None:
    d, rcd = _dispatcher()
    rcd.errors["operations/deletefile"] = RcdError("is a directory")
    rcd.responses["operations/purge"] = {}
    assert await d.dispatch("drive_delete", {"handle": "folder"}) == {"deleted": True}
    endpoints = [c[0] for c in rcd.calls]
    assert "operations/deletefile" in endpoints
    assert "operations/purge" in endpoints


async def test_drive_delete_reraises_unknown_error() -> None:
    d, rcd = _dispatcher()
    rcd.errors["operations/deletefile"] = RcdError("network down")
    with pytest.raises(RpcError, match="network down"):
        await d.dispatch("drive_delete", {"handle": "missing.txt"})


async def test_drive_delete_denied_when_read_only() -> None:
    d, _ = _dispatcher(access=Access.READ)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_delete", {"handle": "x.txt"})


# --- rcd error mapping ---------------------------------------------------

async def test_rcd_auth_error_maps_to_auth_rpcerror() -> None:
    d, rcd = _dispatcher()
    rcd.errors["operations/list"] = RcdAuthError("trust token revoked")
    with pytest.raises(RpcError) as info:
        await d.dispatch("drive_list", {})
    assert info.value.code == "AUTH"


async def test_rcd_generic_error_maps_to_upstream_rpcerror() -> None:
    d, rcd = _dispatcher()
    rcd.errors["operations/list"] = RcdError("rcd hiccup")
    with pytest.raises(RpcError) as info:
        await d.dispatch("drive_list", {})
    assert info.value.code == "UPSTREAM"
