"""Tests for ``brokers/rclone_broker/_verbs.py`` — the dispatcher logic only.

The dispatcher is pure routing: verb name -> rclone invocation -> response
dict, with a per-capability permission gate in the middle. The ``rclone``
subprocess itself is never run here — ``_run_rclone`` / ``_run_rclone_raw``
are stubbed so what's under test is the dispatcher.
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
    _validate_local_path,
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


# --- remote path validation -------------------------------------------------

def test_remote_path_simple() -> None:
    assert _validate_remote_path("Documents/notes.txt") == "Documents/notes.txt"


def test_remote_path_root_is_empty_string() -> None:
    assert _validate_remote_path("") == ""


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/../b", ".."])
def test_remote_path_traversal_blocked(bad: str) -> None:
    with pytest.raises(RpcError, match="path traversal"):
        _validate_remote_path(bad)


# --- local path validation --------------------------------------------------

def test_local_path_under_downloads_allowed(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = downloads / "f.txt"
    target.write_text("hi")
    assert _validate_local_path(target, downloads, tmp_path / "home") == target.resolve()


def test_local_path_under_agent_home_allowed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _validate_local_path(home / "f.txt", tmp_path / "downloads", home) == (home / "f.txt").resolve()


def test_local_path_outside_allowed_roots_rejected(tmp_path: Path) -> None:
    with pytest.raises(RpcError, match="local path not allowed"):
        _validate_local_path(Path("/etc/passwd"), tmp_path / "downloads", tmp_path / "home")


# --- permission gate --------------------------------------------------------

async def test_unknown_verb_raises() -> None:
    with pytest.raises(RpcError, match="unknown verb"):
        await _dispatcher().dispatch("nope", {})


async def test_read_verb_denied_without_drive_access() -> None:
    with pytest.raises(RpcError, match="PERMISSION_DENIED|requires drive"):
        await _dispatcher(access=Access.OFF).dispatch("list_directory", {"path": ""})


async def test_write_verb_denied_when_read_only() -> None:
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await _dispatcher(access=Access.READ).dispatch("delete", {"remote_path": "x.txt"})


async def test_read_verb_allowed_when_read_only() -> None:
    d = _dispatcher(access=Access.READ)
    d._run_rclone = AsyncMock(return_value=(0, "[]", ""))
    assert "items" in await d.dispatch("list_directory", {"path": ""})


async def test_write_verb_allowed_when_read_write() -> None:
    d = _dispatcher(access=Access.READ_WRITE)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    assert await d.dispatch("mkdir", {"remote_path": "d"}) == {"created": True}


# --- read verbs -------------------------------------------------------------

async def test_list_directory() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, json.dumps([
        {"Name": "file.txt", "Size": 100, "IsDir": False, "ModTime": "2024-01-01T00:00:00Z"},
        {"Name": "folder", "Size": 0, "IsDir": True, "ModTime": "2024-01-01T00:00:00Z"},
    ]), ""))
    result = await d.dispatch("list_directory", {"path": "Documents"})
    assert [i["name"] for i in result["items"]] == ["file.txt", "folder"]
    assert result["items"][1]["is_dir"] is True


async def test_about() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, json.dumps({"total": 1000, "used": 600, "free": 400}), ""))
    assert await d.dispatch("about", {}) == {"total_bytes": 1000, "used_bytes": 600, "free_bytes": 400}


async def test_search() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, "Documents/notes.txt\nPhotos/x.jpg\n", ""))
    result = await d.dispatch("search", {"pattern": "*.txt", "path": ""})
    assert result == {"matches": ["Documents/notes.txt", "Photos/x.jpg"], "count": 2}


async def test_size() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, json.dumps({"count": 42, "bytes": 1234567}), ""))
    assert await d.dispatch("size", {"path": "Documents"}) == {"count": 42, "bytes": 1234567}


async def test_cat_roundtrips_content() -> None:
    d = _dispatcher()
    d._run_rclone_raw = AsyncMock(return_value=b"hello world")
    result = await d.dispatch("cat", {"remote_path": "f.txt"})
    assert result["encoding"] == "base64"
    assert result["truncated"] is False
    assert result["size"] == 11
    assert base64.b64decode(result["content"]) == b"hello world"


async def test_cat_binary_survives_roundtrip() -> None:
    d = _dispatcher()
    blob = bytes([0x00, 0x80, 0xFF, 0x41])
    d._run_rclone_raw = AsyncMock(return_value=blob)
    result = await d.dispatch("cat", {"remote_path": "b.bin"})
    assert base64.b64decode(result["content"]) == blob


async def test_cat_truncates_at_max_bytes() -> None:
    d = _dispatcher()
    d._run_rclone_raw = AsyncMock(return_value=b"x" * 2000)
    result = await d.dispatch("cat", {"remote_path": "big.txt", "max_bytes": 100})
    assert result["truncated"] is True
    assert result["size"] == 2000
    assert len(base64.b64decode(result["content"])) == 100


async def test_cat_rejects_missing_remote_path() -> None:
    with pytest.raises(RpcError, match="required"):
        await _dispatcher().dispatch("cat", {})


async def test_cat_rejects_bad_max_bytes() -> None:
    with pytest.raises(RpcError, match="max_bytes"):
        await _dispatcher().dispatch("cat", {"remote_path": "f.txt", "max_bytes": 0})


async def test_verb_propagates_path_traversal() -> None:
    with pytest.raises(RpcError, match="path traversal"):
        await _dispatcher().dispatch("list_directory", {"path": "../secret"})


# --- write verbs ------------------------------------------------------------

async def test_mkdir() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    assert await d.dispatch("mkdir", {"remote_path": "new"}) == {"created": True}


async def test_delete_file() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    assert await d.dispatch("delete", {"remote_path": "f.txt"}) == {"deleted": True}


async def test_delete_falls_back_to_purge_for_directory() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(side_effect=[(1, "", "Is a directory"), (0, "", "")])
    assert await d.dispatch("delete", {"remote_path": "folder"}) == {"deleted": True}


async def test_delete_reraises_non_directory_error() -> None:
    d = _dispatcher()
    d._run_rclone = AsyncMock(return_value=(1, "", "object not found"))
    with pytest.raises(RpcError, match="object not found"):
        await d.dispatch("delete", {"remote_path": "missing.txt"})


async def test_copy_from_remote_defaults_local_name(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    d = _dispatcher(downloads_dir=downloads)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    downloads.mkdir(parents=True)
    (downloads / "report.txt").write_bytes(b"hello world")
    result = await d.dispatch("copy_from_remote", {"remote_path": "a/b/report.txt"})
    assert result == {"local_path": str(downloads / "report.txt"), "bytes_copied": 11}


async def test_copy_from_remote_honors_explicit_local_path(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    d = _dispatcher(downloads_dir=downloads)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    downloads.mkdir(parents=True)
    custom = downloads / "named.txt"
    custom.write_bytes(b"custom")
    result = await d.dispatch("copy_from_remote", {"remote_path": "orig.txt", "local_path": str(custom)})
    assert result == {"local_path": str(custom), "bytes_copied": 6}


async def test_move_from_remote(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    d = _dispatcher(downloads_dir=downloads)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    downloads.mkdir(parents=True)
    (downloads / "m.txt").write_bytes(b"moved")
    result = await d.dispatch("move_from_remote", {"remote_path": "m.txt"})
    assert result == {"local_path": str(downloads / "m.txt"), "bytes_moved": 5}


async def test_copy_to_remote(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    d = _dispatcher(downloads_dir=downloads)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    downloads.mkdir(parents=True)
    src = downloads / "up.txt"
    src.write_bytes(b"upload content")
    result = await d.dispatch("copy_to_remote", {"local_path": str(src), "remote_path": "Docs/up.txt"})
    assert result == {"remote_path": "Docs/up.txt", "bytes_copied": 14}


async def test_move_to_remote(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    d = _dispatcher(downloads_dir=downloads)
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    downloads.mkdir(parents=True)
    src = downloads / "mv.txt"
    src.write_bytes(b"move upload content")
    result = await d.dispatch("move_to_remote", {"local_path": str(src), "remote_path": "Archive/mv.txt"})
    assert result == {"remote_path": "Archive/mv.txt", "bytes_moved": 19}


async def test_copy_to_remote_rejects_missing_local_file(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path / "downloads")
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    with pytest.raises(RpcError, match="local file not found"):
        await d.dispatch("copy_to_remote", {
            "local_path": str(tmp_path / "downloads" / "nope.txt"),
            "remote_path": "Docs/x.txt",
        })


async def test_copy_to_remote_rejects_disallowed_local_path(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path / "downloads")
    d._run_rclone = AsyncMock(return_value=(0, "", ""))
    with pytest.raises(RpcError, match="local path not allowed"):
        await d.dispatch("copy_to_remote", {"local_path": "/etc/hosts", "remote_path": "Docs/x.txt"})


# --- canonical (drive_*) verbs ---------------------------------------------

from integrations.brokers.rclone_broker._verbs import _join_remote_path, _rclone_entry


def test_join_remote_path() -> None:
    assert _join_remote_path("", "a.txt") == "a.txt"
    assert _join_remote_path("Docs", "a.txt") == "Docs/a.txt"
    assert _join_remote_path("Docs/", "a.txt") == "Docs/a.txt"


def test_rclone_entry_shape() -> None:
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


def test_rclone_entry_root_parent() -> None:
    entry = _rclone_entry({"Name": "x", "IsDir": True}, parent_path="")
    assert entry["handle"] == "x" and entry["is_dir"] is True


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
    # The lsjson call should have targeted the subdir.
    assert d._run_rclone.await_args.args[1] == "default:Documents"


async def test_drive_download_writes_to_disk(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    async def fake_rclone(*args, check=True):  # noqa: ANN001, ANN002
        # When rclone "downloads", produce the local file ourselves so .stat() works.
        (tmp_path / "report.pdf").write_bytes(b"hello world")
        return 0, "", ""
    d._run_rclone = fake_rclone
    result = await d.dispatch("drive_download", {"handle": "Docs/report.pdf"})
    assert result["filename"] == "report.pdf"
    assert result["size"] == 11
    assert Path(result["local_path"]).read_bytes() == b"hello world"


async def test_drive_upload_decodes_b64_and_cleans_scratch(tmp_path: Path) -> None:
    d = _dispatcher(downloads_dir=tmp_path)
    seen_scratch: list[Path] = []

    async def fake_rclone(*args, check=True):  # noqa: ANN001, ANN002
        # During the call the scratch file must exist on disk.
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
    # Scratch file is gone after the call.
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


async def test_drive_delete_denied_when_read_only(tmp_path: Path) -> None:
    d = _dispatcher(access=Access.READ, downloads_dir=tmp_path)
    with pytest.raises(RpcError, match="requires drive:read_write"):
        await d.dispatch("drive_delete", {"handle": "x.txt"})
