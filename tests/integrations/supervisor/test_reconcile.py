"""End-to-end tests for ``Supervisor`` startup reconciliation.

Each test stages a vault by running one supervisor (the "first boot"),
stops it, then starts a second supervisor against the same vault dir and
asserts what the second one rehydrates. Both supervisors talk to a real
``FakeEmail`` broker, so the spawn / IMAP-login / READY handshake
exercises the production path end-to-end.
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
    """Length-prefixed JSON RPC: open, send, read, close."""
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        req = json.dumps({"id": 1, "verb": verb, "args": args}).encode("utf-8")
        writer.write(len(req).to_bytes(4, "big") + req)
        await writer.drain()
        length = int.from_bytes(await reader.readexactly(4), "big")
        return json.loads(await reader.readexactly(length))
    finally:
        writer.close()
        await writer.wait_closed()


def _test_catalog(fake: FakeEmail) -> dict[str, CatalogEntry]:
    """A catalog with one ``icloud`` entry pointed at the local fake."""
    return {
        "icloud": CatalogEntry(
            slug="icloud",
            command=["python", "-m", "integrations.brokers.email_broker"],
            capabilities=frozenset({"email"}),
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
        ),
    }


def _make_supervisor(tmp_path: Path, catalog: dict[str, CatalogEntry]) -> Supervisor:
    """Build a Supervisor that points at ``tmp_path``-relative vault + sockets.

    Both supervisors in a reconcile test reuse the same ``tmp_path``, so the
    vault on disk persists across the stop / start boundary while the
    sockets dir is wiped tmpfs-style by the second supervisor.
    """
    return Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        catalog=catalog,
    )


@pytest.mark.asyncio
async def test_reconcile_respawns_persisted_integration(tmp_path: Path) -> None:
    """Add → stop → restart → the integration is back without re-add.

    Proves the load-bearing claim: container restart no longer loses the
    user's connections. After the second supervisor's start() returns,
    ``list`` surfaces the same id and the broker socket is reachable.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        sup1 = _make_supervisor(tmp_path, _test_catalog(fake))
        await sup1.start()
        try:
            add_resp = await _rpc_call(
                sup1.app_sock_path,
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
        finally:
            await sup1.stop()

        # Vault files persist; broker subprocess is gone.
        assert meta_path(sup1.vault_dir, "icloud_personal").exists()
        assert enc_path(sup1.vault_dir, "icloud_personal").exists()

        sup2 = _make_supervisor(tmp_path, _test_catalog(fake))
        await sup2.start()
        try:
            # Registry is rehydrated — list shows the integration.
            list_resp = await _rpc_call(sup2.app_sock_path, "list", {})
            integrations = list_resp["result"]["integrations"]
            assert len(integrations) == 1
            assert integrations[0]["id"] == "icloud_personal"

            # Broker is up — calling list_mailboxes against its socket works.
            broker_socket = Path(integrations[0]["socket"])
            assert broker_socket.exists()
            mb_resp = await _rpc_call(broker_socket, "list_mailboxes", {})
            assert "error" not in mb_resp, mb_resp
            assert sorted(m["name"] for m in mb_resp["result"]["mailboxes"]) == [
                "INBOX",
                "Sent",
                "Trash",
            ]
        finally:
            await sup2.stop()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_reconcile_skips_integration_when_slug_missing_from_catalog(
    tmp_path: Path,
) -> None:
    """Catalog drift (slug removed) → that integration is skipped, others load.

    The vault entry stays on disk so the user can re-add (or a future
    catalog can re-introduce the slug) without losing credentials.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        sup1 = _make_supervisor(tmp_path, _test_catalog(fake))
        await sup1.start()
        try:
            add_resp = await _rpc_call(
                sup1.app_sock_path,
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
        finally:
            await sup1.stop()

        # Second supervisor with an empty catalog — slug "icloud" is gone.
        sup2 = _make_supervisor(tmp_path, {})
        await sup2.start()
        try:
            list_resp = await _rpc_call(sup2.app_sock_path, "list", {})
            assert list_resp["result"]["integrations"] == []
        finally:
            await sup2.stop()

        # Vault files weren't deleted — credentials are preserved.
        assert meta_path(sup1.vault_dir, "icloud_personal").exists()
        assert enc_path(sup1.vault_dir, "icloud_personal").exists()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_reconcile_skips_integration_when_auth_now_rejected(
    tmp_path: Path,
) -> None:
    """Upstream auth fails on respawn → integration is skipped, vault persists.

    Mirrors the real-world case where a user's app-password gets rotated
    out from under us. The supervisor stays up; the user's path forward
    is to remove + re-add via the UI.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        sup1 = _make_supervisor(tmp_path, _test_catalog(fake))
        await sup1.start()
        try:
            add_resp = await _rpc_call(
                sup1.app_sock_path,
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
        finally:
            await sup1.stop()

        # Make every subsequent IMAP LOGIN fail — reconcile's broker spawn
        # will exit 77 (auth fail) and we should swallow that gracefully.
        fake.reject_next_n_imap_logins = 99

        sup2 = _make_supervisor(tmp_path, _test_catalog(fake))
        await sup2.start()
        try:
            list_resp = await _rpc_call(sup2.app_sock_path, "list", {})
            assert list_resp["result"]["integrations"] == []
        finally:
            await sup2.stop()

        # Vault files preserved so the user can fix things by re-adding.
        assert meta_path(sup1.vault_dir, "icloud_personal").exists()
        assert enc_path(sup1.vault_dir, "icloud_personal").exists()
    finally:
        await fake.stop()
