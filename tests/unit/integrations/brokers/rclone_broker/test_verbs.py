"""Tests for ``brokers/rclone_broker/_verbs.py`` — the dispatcher logic only.

The dispatcher is pure routing: verb name -> rclone invocation -> response
dict, with a per-capability permission gate in the middle. The ``rclone``
subprocess itself is never run here — ``_run_rclone`` is stubbed so what's
under test is the dispatcher.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from integrations._rpc import RpcError
from integrations.brokers.rclone_broker._verbs import (
    VerbDispatcher,
    _join_remote_path,
    _rclone_entry,
    _validate_remote_path,
)
from integrations.permissions import Access, Capability


def _dispatcher(
    *,
    access: Access = Access.READ_WRITE,
    downloads_dir: Path = Path("/tmp/rclone-downloads"),
) -> VerbDispatcher:
    perms = {Capability.DRIVE: access} if access != Access.OFF else {}
    return VerbDispatcher(permissions=perms, downloads_dir=downloads_dir)


# --- remote path validation ------------------------------------------------

def test_remote_path_simple() -> None:
    assert _validate_remote_path("Documents/notes.txt") == "Documents/notes.txt"


def test_remote_path_root_is_empty_string() -> None:
    assert _validate_remote_path("") == ""


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/../b", ".."])
def test_remote_path_traversal_blocked(bad: str) -> None:
    with pytest.raises(RpcError, match="path traversal"):
        _validate_remote_path(bad)


# --- helpers ---------------------------------------------------------------

def test_join_remote_path_no_parent() -> None:
    assert _join_remote_path("", "a.txt") == "a.txt"


def test_join_remote_path_inserts_slash() -> None:
    assert _join_remote_path("Docs", "a.txt") == "Docs/a.txt"


def test_join_remote_path_keeps_trailing_slash() -> None:
    assert _join_remote_path("Docs/", "a.txt") == "Docs/a.txt"


def test_rclone_entry_file() -> None:
    entry = _rclone_entry(
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


def test_rclone_entry_root_parent_keeps_bare_name() -> None:
    entry = _rclone_entry({"Name": "x", "IsDir": True}, parent_path="")
    assert entry["handle"] == "x"
    assert entry["is_dir"] is True


# --- permission gate -------------------------------------------------------

async def test_unknown_verb_raises() -> None:
    with pytest.raises(RpcError, match="unknown verb"):
        await _dispatcher().dispatch("nope", {})


async def test_read_verb_denied_without_drive_access() -> None:
    with pytest.raises(RpcError, match="PERMISSION_DENIED|requires drive"):
        await _dispatcher(access=Access.OFF).dispatch("drive_list", {})


async def test_write_verb_denied_when_read_only() -> None:
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await _dispatcher(access=Access.READ).dispatch(
            "drive_delete", {"handle": "x.txt"},
        )


async def test_read_verb_allowed_when_read_only() -> None:
    d = _dispatcher(access=Access.READ)
    d._run_rclone = AsyncMock(return_value=(0, "[]", ""))
    assert "entries" in await d.dispatch("drive_list", {})


async def test_write_verb_allowed_when_read_write() -> None:
    d = _dispatcher(access=Access.READ_WRITE)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    assert (await d.dispatch("drive_mkdir", {"name": "d"}))["entry"]["is_dir"] is True


# --- drive_list ------------------------------------------------------------

async def test_drive_list_no_pattern(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, json.dumps([
        {"Name": "a.txt", "Size": 10, "IsDir": False, "ModTime": ""},
        {"Name": "Sub", "Size": 0, "IsDir": True, "ModTime": ""},
    ]), ""))
    result = await d.dispatch("drive_list", {})
    assert [e["name"] for e in result["entries"]] == ["a.txt", "Sub"]
    assert result["entries"][0]["handle"] == "a.txt"
    assert result["entries"][1]["is_dir"] is True


async def test_drive_list_with_pattern_passes_include(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "[]", ""))
    await d.dispatch("drive_list", {"pattern": "report"})
    args = d._run_rclone.await_args.args
    assert "--include" in args
    assert args[args.index("--include") + 1] == "*report*"


async def test_drive_list_with_handle_scopes_to_subdir(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, json.dumps([
        {"Name": "leaf.txt", "Size": 1, "IsDir": False, "ModTime": ""},
    ]), ""))
    result = await d.dispatch("drive_list", {"handle": "Documents"})
    assert result["entries"][0]["handle"] == "Documents/leaf.txt"
    assert d._run_rclone.await_args.args[1] == "default:Documents"


async def test_drive_list_traversal_blocked(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    with pytest.raises(RpcError, match="path traversal"):
        await d.dispatch("drive_list", {"handle": "../secret"})


# --- drive_download --------------------------------------------------------

async def test_drive_download_writes_to_disk(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    async def fake_rclone(*args, check=True):  # noqa: ANN001, ANN002
        (tmp_path / "report.pdf").write_bytes(b"hello world")
        return 0, "", ""
    d._run_rclone = fake_rclone
    result = await d.dispatch("drive_download", {"handle": "Docs/report.pdf"})
    assert result["filename"] == "report.pdf"
    assert result["size"] == 11
    assert Path(result["local_path"]).read_bytes() == b"hello world"


async def test_drive_download_requires_handle(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    with pytest.raises(RpcError, match="required"):
        await d.dispatch("drive_download", {})


# --- drive_upload ----------------------------------------------------------

async def test_drive_upload_decodes_b64_and_cleans_scratch(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    seen_scratch: list[Path] = []

    async def fake_rclone(*args, check=True):  # noqa: ANN001, ANN002
        local = Path(args[1])
        assert local.exists(), "scratch file missing during rclone call"
        seen_scratch.append(local)
        return 0, "", ""

    d._run_rclone = fake_rclone
    payload = b"file content"
    result = await d.dispatch("drive_upload", {
        "name": "up.txt", "data_b64": base64.b64encode(payload).decode(),
        "parent_handle": "Docs", "mime_type": "text/plain",
    })
    assert result["entry"] == {
        "name": "up.txt", "handle": "Docs/up.txt", "is_dir": False,
        "size": len(payload), "mime_type": "text/plain", "modified": "",
    }
    assert seen_scratch and not seen_scratch[0].exists()


async def test_drive_upload_cleans_scratch_on_failure(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    seen: list[Path] = []

    async def fake_rclone(*args, check=True):  # noqa: ANN001, ANN002
        seen.append(Path(args[1]))
        raise RpcError("UPSTREAM", "rclone error: nope")

    d._run_rclone = fake_rclone
    with pytest.raises(RpcError):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": base64.b64encode(b"x").decode(), "parent_handle": "",
        })
    assert seen and not seen[0].exists()


async def test_drive_upload_rejects_bad_base64(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    with pytest.raises(RpcError, match="invalid base64"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": "not!!base64!!", "parent_handle": "",
        })


async def test_drive_upload_denied_when_read_only(tmp_path: Path) -> None:
    d = _dispatcher(access=Access.READ, downloads_dir=tmp_path)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_upload", {
            "name": "x", "data_b64": base64.b64encode(b"x").decode(), "parent_handle": "",
        })


# --- drive_mkdir, drive_move, drive_delete ---------------------------------

async def test_drive_mkdir(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    result = await d.dispatch("drive_mkdir", {"parent_handle": "Docs", "name": "New"})
    assert result["entry"]["handle"] == "Docs/New"
    assert result["entry"]["is_dir"] is True


async def test_drive_move_renames(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    result = await d.dispatch("drive_move", {
        "handle": "Inbox/a.txt", "dest_parent_handle": "Archive", "name": "b.txt",
    })
    assert result["entry"]["handle"] == "Archive/b.txt"
    args = d._run_rclone.await_args.args
    assert args[1] == "default:Inbox/a.txt"
    assert args[2] == "default:Archive/b.txt"


async def test_drive_move_keeps_name_when_omitted(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    result = await d.dispatch("drive_move", {
        "handle": "Inbox/a.txt", "dest_parent_handle": "Archive",
    })
    assert result["entry"]["name"] == "a.txt"
    assert result["entry"]["handle"] == "Archive/a.txt"


async def test_drive_delete_file(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    assert await d.dispatch("drive_delete", {"handle": "x.txt"}) == {"deleted": True}


async def test_drive_delete_falls_back_to_purge(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(side_effect=[(1, "", "Is a directory"), (0, "", "")])
    assert await d.dispatch("drive_delete", {"handle": "folder"}) == {"deleted": True}


async def test_drive_delete_reraises_non_directory_error(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    d._run_rclone = AsyncMock(return_value=(1, "", "object not found"))
    with pytest.raises(RpcError, match="object not found"):
        await d.dispatch("drive_delete", {"handle": "missing.txt"})


async def test_drive_delete_denied_when_read_only(tmp_path: Path) -> None:
    d = _dispatcher(access=Access.READ, downloads_dir=tmp_path)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_delete", {"handle": "x.txt"})
