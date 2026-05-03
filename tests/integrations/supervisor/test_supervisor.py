"""End-to-end integration test for the supervisor walking skeleton.

Exercises the whole vertical slice in one test:

- Start a real ``Supervisor`` instance in-process with a ``tmp_path`` vault.
- Inject a test catalog that points the email_broker at ``FakeEmail``'s random
  ports with TLS off, so we use the real broker binary against a local fake.
- Call ``add`` over the supervisor's ``app.sock`` — this causes the supervisor
  to write vault files, spawn a real ``python -m integrations.brokers.email_broker``
  subprocess, wait for its ``READY`` sentinel, and register it.
- Call ``resolve`` to get the broker's UDS path back from the supervisor.
- Call ``list_mailboxes`` directly against that broker — proves the app-server
  side of the flow (broker_client will replicate this call shape).
- Call ``list`` and ``remove`` on the supervisor; verify the broker dies and
  vault files disappear.

Nothing mocked at the socket layer. Fakes only at the external-network boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from integrations.supervisor._catalog import CatalogEntry
from integrations.supervisor._lifecycle import Supervisor
from integrations.supervisor._store import enc_path, meta_path
from tests.integrations.fixtures._host_paths import (
    EMAIL_BROKER_HOST_PATHS,
    make_host_paths,
)
from tests.integrations.fixtures.fake_email import FakeEmail


async def _rpc_call(socket_path: Path, verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """Send one length-prefixed JSON frame, read one response, close.

    Same wire format as the app server's ``broker_client`` will use — this helper
    is deliberately small so the test has no dependency on client-side code that
    hasn't been written yet.
    """
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        req = json.dumps({"id": 1, "verb": verb, "args": args}).encode("utf-8")
        writer.write(len(req).to_bytes(4, "big") + req)
        await writer.drain()
        length = int.from_bytes(await reader.readexactly(4), "big")
        body = await reader.readexactly(length)
        return json.loads(body)
    finally:
        writer.close()
        await writer.wait_closed()


def _test_catalog(fake: FakeEmail) -> dict[str, CatalogEntry]:
    """Build a catalog that points the email broker at ``fake``'s random ports.

    Equivalent to the real iCloud catalog entry, but with the fake's host/port
    substituted in and TLS turned off — the fake speaks plaintext IMAP/SMTP.
    """
    return {
        "icloud": CatalogEntry(
            slug="icloud",
            command=["python", "-m", "integrations.brokers.email_broker"],
            static_env={
                "IMAP_HOST": fake.imap_host,
                "IMAP_PORT": str(fake.imap_port),
                "SMTP_HOST": fake.smtp_host,
                "SMTP_PORT": str(fake.smtp_port),
                "IMAP_TLS": "false",
                "SMTP_STARTTLS": "false",
            },
            env_injection={
                "email": "EMAIL_USER",
                "password": "EMAIL_PASS",
            },
            host_paths=EMAIL_BROKER_HOST_PATHS,
        ),
    }


@pytest.mark.asyncio
async def test_add_then_call_broker_then_resolve_then_remove(tmp_path: Path) -> None:
    """The full end-to-end slice: add -> call broker -> resolve -> list -> remove."""
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        # --- add ---
        add_resp = await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "iCloud test",
                "auth_blob": {"email": fake.user, "password": fake.password},
                "write_allowed": False,
            },
        )
        assert "error" not in add_resp, add_resp
        result = add_resp["result"]
        assert result["id"] == "icloud_personal"
        broker_socket = Path(result["socket"])
        assert broker_socket.exists()
        # Vault files landed on disk.
        assert meta_path(sup.vault_dir, "icloud_personal").exists()
        assert enc_path(sup.vault_dir, "icloud_personal").exists()

        # --- call broker directly: the real payoff of the walking skeleton ---
        mb_resp = await _rpc_call(broker_socket, "list_mailboxes", {})
        assert "error" not in mb_resp, mb_resp
        names = sorted(m["name"] for m in mb_resp["result"]["mailboxes"])
        assert names == ["INBOX", "Sent", "Trash"]

        # --- resolve returns the same socket ---
        resolve_resp = await _rpc_call(
            sup.app_sock_path, "resolve", {"id": "icloud_personal"},
        )
        assert resolve_resp["result"] == {
            "id": "icloud_personal",
            "socket": str(broker_socket),
            "write_allowed": False,
        }

        # --- list surfaces the integration ---
        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        integrations = list_resp["result"]["integrations"]
        assert len(integrations) == 1
        assert integrations[0]["id"] == "icloud_personal"
        assert integrations[0]["write_allowed"] is False

        # --- remove kills the broker and deletes vault files ---
        remove_resp = await _rpc_call(
            sup.app_sock_path, "remove", {"id": "icloud_personal"},
        )
        assert remove_resp["result"] == {"id": "icloud_personal"}
        assert not meta_path(sup.vault_dir, "icloud_personal").exists()
        assert not enc_path(sup.vault_dir, "icloud_personal").exists()

        # --- resolve now returns NOT_FOUND ---
        resolve_after = await _rpc_call(
            sup.app_sock_path, "resolve", {"id": "icloud_personal"},
        )
        assert resolve_after["error"]["code"] == "NOT_FOUND"
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_add_with_bad_credentials_returns_auth_error(tmp_path: Path) -> None:
    """Broker LOGIN fails -> it exits 77 -> supervisor surfaces AUTH error and
    rolls back vault state so the user can retry cleanly.
    """
    fake = FakeEmail()
    await fake.start()
    # Force the next LOGIN to be rejected.
    fake.reject_next_n_imap_logins = 99
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        resp = await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "iCloud bad",
                "auth_blob": {"email": fake.user, "password": "wrong"},
                "write_allowed": False,
            },
        )
        assert resp["error"]["code"] == "AUTH"
        # Rollback: no vault files should exist.
        assert not meta_path(sup.vault_dir, "icloud_personal").exists()
        assert not enc_path(sup.vault_dir, "icloud_personal").exists()
        # And the registry is empty.
        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        assert list_resp["result"]["integrations"] == []
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_add_with_unknown_slug_returns_bad_request(tmp_path: Path) -> None:
    """A slug that's not in the injected catalog fails before any vault I/O."""
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        resp = await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "made_up_provider",
                "user_suffix": "x",
                "label": "x",
                "auth_blob": {},
                "write_allowed": False,
            },
        )
        assert resp["error"]["code"] == "BAD_REQUEST"
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_resolve_unknown_id_returns_not_found(tmp_path: Path) -> None:
    """Looking up an integration that was never added returns NOT_FOUND."""
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog={},  # empty catalog is fine; resolve doesn't touch it
    )
    await sup.start()
    try:
        resp = await _rpc_call(
            sup.app_sock_path, "resolve", {"id": "never_added"},
        )
        assert resp["error"]["code"] == "NOT_FOUND"
    finally:
        await sup.stop()


@pytest.mark.asyncio
async def test_update_flips_write_allowed_and_respawns_broker(tmp_path: Path) -> None:
    """``update {id, write_allowed}`` rewrites meta on disk, replaces the
    broker subprocess with a new one carrying the new ``WRITE_ALLOWED`` env,
    and the broker's WRITE_DENIED gate now reflects the flip.

    Strategy: add with write_allowed=False, observe send_message returns
    WRITE_DENIED, flip to True via update, observe send_message no longer
    returns WRITE_DENIED. Different broker PID before vs after proves the
    respawn happened.
    """
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        add_resp = await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "iCloud test",
                "auth_blob": {"email": fake.user, "password": fake.password},
                "write_allowed": False,
            },
        )
        assert "error" not in add_resp, add_resp
        old_pid = sup._registry.get("icloud_personal").broker.proc.pid
        broker_socket_old = Path(add_resp["result"]["socket"])

        # Confirm the gate is currently active: send_message → WRITE_DENIED.
        denied = await _rpc_call(
            broker_socket_old,
            "send_message",
            {"to": ["a@b.com"], "subject": "x", "body": "y"},
        )
        assert denied["error"]["code"] == "WRITE_DENIED"

        # Flip the policy.
        upd_resp = await _rpc_call(
            sup.app_sock_path,
            "update",
            {"id": "icloud_personal", "write_allowed": True},
        )
        assert "error" not in upd_resp, upd_resp
        assert upd_resp["result"]["write_allowed"] is True

        # New broker with a different PID is now serving.
        new_record = sup._registry.get("icloud_personal")
        assert new_record.broker.proc.pid != old_pid
        assert new_record.state == "running"

        # Old socket got rebound to the new broker — WRITE_DENIED is gone.
        broker_socket_new = Path(upd_resp["result"]["socket"])
        send_resp = await _rpc_call(
            broker_socket_new,
            "send_message",
            {"to": ["a@b.com"], "subject": "x", "body": "y"},
        )
        assert "error" not in send_resp, send_resp
        assert send_resp["result"]["sent"] is True

        # On-disk meta reflects the new policy too — would survive restart.
        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        listed = next(
            i for i in list_resp["result"]["integrations"]
            if i["id"] == "icloud_personal"
        )
        assert listed["write_allowed"] is True
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_update_unknown_id_returns_not_found(tmp_path: Path) -> None:
    """``update`` against an integration that doesn't exist is NOT_FOUND."""
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog={},
    )
    await sup.start()
    try:
        resp = await _rpc_call(
            sup.app_sock_path,
            "update",
            {"id": "never_added", "write_allowed": True},
        )
        assert resp["error"]["code"] == "NOT_FOUND"
    finally:
        await sup.stop()


@pytest.mark.asyncio
async def test_update_changes_label_via_app_sock(tmp_path: Path) -> None:
    """``update {id, label}`` rewrites the on-disk meta and ``list`` reflects
    the new label. Label is meta-only (the broker never sees it), so this
    path doesn't go through respawn.
    """
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "Original",
                "auth_blob": {"email": fake.user, "password": fake.password},
                "write_allowed": False,
            },
        )

        upd_resp = await _rpc_call(
            sup.app_sock_path,
            "update",
            {"id": "icloud_personal", "label": "Renamed"},
        )
        assert "error" not in upd_resp, upd_resp
        assert upd_resp["result"]["label"] == "Renamed"

        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        listed = next(
            i for i in list_resp["result"]["integrations"]
            if i["id"] == "icloud_personal"
        )
        assert listed["label"] == "Renamed"
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_update_rejects_empty_body(tmp_path: Path) -> None:
    """``update {id}`` with no fields to change is BAD_REQUEST — caller has
    to specify at least one of write_allowed or label."""
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "iCloud",
                "auth_blob": {"email": fake.user, "password": fake.password},
                "write_allowed": False,
            },
        )

        resp = await _rpc_call(
            sup.app_sock_path, "update", {"id": "icloud_personal"},
        )
        assert resp["error"]["code"] == "BAD_REQUEST"
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_update_no_op_when_value_unchanged(tmp_path: Path) -> None:
    """Setting ``write_allowed`` to its current value doesn't restart the
    broker — the manager short-circuits and returns the existing record.
    No respawn means the broker PID is unchanged.
    """
    fake = FakeEmail()
    await fake.start()
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        host_paths=make_host_paths(tmp_path),
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        await _rpc_call(
            sup.app_sock_path,
            "add",
            {
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "iCloud test",
                "auth_blob": {"email": fake.user, "password": fake.password},
                "write_allowed": False,
            },
        )
        old_pid = sup._registry.get("icloud_personal").broker.proc.pid

        upd_resp = await _rpc_call(
            sup.app_sock_path,
            "update",
            {"id": "icloud_personal", "write_allowed": False},
        )
        assert "error" not in upd_resp, upd_resp
        assert sup._registry.get("icloud_personal").broker.proc.pid == old_pid
    finally:
        await sup.stop()
        await fake.stop()
