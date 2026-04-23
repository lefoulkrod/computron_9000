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
            },
            env_injection={
                "email": "EMAIL_USER",
                "password": "EMAIL_PASS",
            },
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
