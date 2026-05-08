"""Unit tests for the Drive write tools (upload_file, create_folder).

Same pattern as ``test_email_tools.py``: stub ``broker_client.call``
to return canned shapes (or raise) and assert on the resulting string.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.drive.create_folder import create_drive_folder
from tools.integrations.drive.share_file import share_drive_file
from tools.integrations.drive.trash_file import trash_drive_file
from tools.integrations.drive.update_file import update_drive_file
from tools.integrations.drive.upload_file import upload_drive_file


def _patch_call(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: Any = None,
    exc: Exception | None = None,
) -> None:
    async def _fake(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)


# ── upload_drive_file ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_confirms_with_file_id_and_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_call(
        monkeypatch,
        result={"file": {"id": "abc123", "name": "report.txt"}},
    )
    f = tmp_path / "report.txt"
    f.write_text("hello world")

    out = await upload_drive_file("gw_work", str(f))
    assert "abc123" in out
    assert "report.txt" in out
    assert "11B" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_uses_custom_name_when_provided(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "x"}}

    monkeypatch.setattr(broker_client, "call", _capture)

    f = tmp_path / "local.txt"
    f.write_text("data")
    out = await upload_drive_file("gw_work", str(f), name="renamed.txt")

    assert captured["name"] == "renamed.txt"
    assert "renamed.txt" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_sends_base64_content_and_mime_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "x"}}

    monkeypatch.setattr(broker_client, "call", _capture)

    payload = b"\x89PNG fake"
    f = tmp_path / "image.png"
    f.write_bytes(payload)
    await upload_drive_file("gw_work", str(f))

    assert base64.b64decode(captured["data_b64"]) == payload
    assert captured["mime_type"] == "image/png"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_passes_parent_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "x"}}

    monkeypatch.setattr(broker_client, "call", _capture)

    f = tmp_path / "doc.txt"
    f.write_text("x")
    await upload_drive_file("gw_work", str(f), parent_id="folder_abc")

    assert captured["parent_id"] == "folder_abc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_reports_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)

    missing = tmp_path / "nope.txt"
    out = await upload_drive_file("gw_work", str(missing))
    assert "Cannot read file" in out
    assert str(missing) in out
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    f = tmp_path / "f.txt"
    f.write_text("x")
    out = await upload_drive_file("gw_unknown", str(f))
    assert out == "Integration 'gw_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_reports_write_denied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    f = tmp_path / "f.txt"
    f.write_text("x")
    out = await upload_drive_file("gw_work", str(f))
    assert out == "Writes are disabled for 'gw_work'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_reports_generic_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("quota exceeded"))
    f = tmp_path / "f.txt"
    f.write_text("x")
    out = await upload_drive_file("gw_work", str(f))
    assert "quota exceeded" in out


# ── create_drive_folder ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_folder_confirms_with_folder_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(
        monkeypatch,
        result={"file": {"id": "folder_xyz"}},
    )
    out = await create_drive_folder("gw_work", "Project Files")
    assert "folder_xyz" in out
    assert "Project Files" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_folder_passes_parent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "x"}}

    monkeypatch.setattr(broker_client, "call", _capture)
    await create_drive_folder("gw_work", "Sub", parent_id="parent_abc")

    assert captured["name"] == "Sub"
    assert captured["parent_id"] == "parent_abc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_folder_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await create_drive_folder("gw_unknown", "Folder")
    assert out == "Integration 'gw_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_folder_reports_write_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await create_drive_folder("gw_work", "Folder")
    assert out == "Writes are disabled for 'gw_work'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_folder_reports_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("boom"))
    out = await create_drive_folder("gw_work", "Folder")
    assert "boom" in out


# ── update_drive_file ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_with_new_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "abc", "name": "report.txt"}}

    monkeypatch.setattr(broker_client, "call", _capture)

    f = tmp_path / "report.txt"
    f.write_text("updated content")
    out = await update_drive_file("gw_work", "abc", file_path=str(f))

    assert base64.b64decode(captured["data_b64"]) == b"updated content"
    assert captured["mime_type"] == "text/plain"
    assert "abc" in out
    assert "report.txt" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_rename_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"file": {"id": "abc", "name": "new_name.txt"}}

    monkeypatch.setattr(broker_client, "call", _capture)
    out = await update_drive_file("gw_work", "abc", name="new_name.txt")

    assert captured["name"] == "new_name.txt"
    assert "data_b64" not in captured
    assert "new_name.txt" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_nothing_to_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)
    out = await update_drive_file("gw_work", "abc")
    assert "Nothing to update" in out
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_missing_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)
    missing = tmp_path / "nope.txt"
    out = await update_drive_file("gw_work", "abc", file_path=str(missing))
    assert "Cannot read file" in out
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await update_drive_file("gw_unknown", "abc", name="x")
    assert out == "Integration 'gw_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_reports_write_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await update_drive_file("gw_work", "abc", name="x")
    assert out == "Writes are disabled for 'gw_work'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_file_reports_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("not found"))
    out = await update_drive_file("gw_work", "abc", name="x")
    assert "not found" in out


# ── trash_drive_file ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trash_file_confirms_with_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(
        monkeypatch,
        result={"file": {"id": "abc", "name": "old_report.pdf"}},
    )
    out = await trash_drive_file("gw_work", "abc")
    assert "old_report.pdf" in out
    assert "trash" in out.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trash_file_passes_file_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured["verb"] = verb
        captured["args"] = args
        return {"file": {"id": "abc"}}

    monkeypatch.setattr(broker_client, "call", _capture)
    await trash_drive_file("gw_work", "abc")
    assert captured["verb"] == "trash_drive_file"
    assert captured["args"]["file_id"] == "abc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trash_file_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await trash_drive_file("gw_unknown", "abc")
    assert out == "Integration 'gw_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trash_file_reports_write_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await trash_drive_file("gw_work", "abc")
    assert out == "Writes are disabled for 'gw_work'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trash_file_reports_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("forbidden"))
    out = await trash_drive_file("gw_work", "abc")
    assert "forbidden" in out


# ── share_drive_file ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_with_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(
        monkeypatch,
        result={"permission": {
            "id": "perm1", "role": "reader", "type": "user",
            "emailAddress": "alice@example.com",
        }},
    )
    out = await share_drive_file(
        "gw_work", "abc", role="reader", share_type="user",
        email="alice@example.com",
    )
    assert "alice@example.com" in out
    assert "reader" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_anyone_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(
        monkeypatch,
        result={"permission": {"id": "perm2", "role": "reader", "type": "anyone"}},
    )
    out = await share_drive_file("gw_work", "abc", role="reader", share_type="anyone")
    assert "anyone" in out
    assert "reader" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_passes_args_to_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"permission": {"id": "x"}}

    monkeypatch.setattr(broker_client, "call", _capture)
    await share_drive_file(
        "gw_work", "abc", role="writer", share_type="user",
        email="bob@example.com",
    )
    assert captured["file_id"] == "abc"
    assert captured["role"] == "writer"
    assert captured["type"] == "user"
    assert captured["email"] == "bob@example.com"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_rejects_invalid_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)
    out = await share_drive_file("gw_work", "abc", role="admin", share_type="user", email="a@b.com")
    assert "Invalid role" in out
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_rejects_invalid_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)
    out = await share_drive_file("gw_work", "abc", role="reader", share_type="public")
    assert "Invalid type" in out
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_requires_email_for_user_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _track(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _track)
    out = await share_drive_file("gw_work", "abc", role="reader", share_type="user")
    assert "email" in out.lower()
    assert called is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await share_drive_file(
        "gw_unknown", "abc", role="reader", share_type="anyone",
    )
    assert out == "Integration 'gw_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_reports_write_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await share_drive_file(
        "gw_work", "abc", role="reader", share_type="anyone",
    )
    assert out == "Writes are disabled for 'gw_work'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_share_file_reports_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("forbidden"))
    out = await share_drive_file(
        "gw_work", "abc", role="reader", share_type="anyone",
    )
    assert "forbidden" in out
