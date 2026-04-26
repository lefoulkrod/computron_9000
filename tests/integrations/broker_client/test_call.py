"""End-to-end tests for ``integrations.broker_client.call()``.

Same integration shape as ``tests/integrations/supervisor/test_supervisor.py``:
real ``Supervisor`` in-process, real ``email_broker`` subprocess, real
``FakeEmail``. The difference is the exerciser — these tests drive the full
stack through ``broker_client.call()`` instead of hand-rolled UDS frames.
If ``call()`` works against this setup, tool handlers will work against a
real iCloud/Gmail too.

The test catalog (``_test_catalog``) and the add-integration RPC helper
(``_rpc_add``) duplicate the shape from ``test_supervisor.py`` rather than
depend on it. Walking-skeleton discipline: each test file stands on its own.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from integrations._rpc import RpcError, serve_rpc
from integrations.supervisor._catalog import CatalogEntry
from integrations.supervisor._lifecycle import Supervisor
from tests.integrations.fixtures.fake_email import FakeEmail


def _test_catalog(fake: FakeEmail) -> dict[str, CatalogEntry]:
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
        ),
    }


async def _rpc_add(
    app_sock_path: Path,
    *,
    user_suffix: str,
    label: str,
    fake: FakeEmail,
    write_allowed: bool = False,
    password_override: str | None = None,
) -> dict[str, Any]:
    """Admin-path ``add`` via the supervisor's ``app.sock``.

    Not a broker_client concern — the app server will expose this as an HTTP
    route, but this test needs a registered integration before it can exercise
    ``call()``. Minimal hand-rolled UDS call.
    """
    reader, writer = await asyncio.open_unix_connection(str(app_sock_path))
    try:
        frame = {
            "id": 1,
            "verb": "add",
            "args": {
                "slug": "icloud",
                "user_suffix": user_suffix,
                "label": label,
                "auth_blob": {
                    "email": fake.user,
                    "password": password_override if password_override is not None else fake.password,
                },
                "write_allowed": write_allowed,
            },
        }
        body = json.dumps(frame).encode("utf-8")
        writer.write(len(body).to_bytes(4, "big") + body)
        await writer.drain()
        length = int.from_bytes(await reader.readexactly(4), "big")
        return json.loads(await reader.readexactly(length))
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_call_list_mailboxes_against_real_broker(tmp_path: Path) -> None:
    """Happy path: broker_client.call -> supervisor.resolve -> broker.list_mailboxes
    -> the seeded ``fake_email`` mailboxes come back through the response."""
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
        add_resp = await _rpc_add(
            sup.app_sock_path, user_suffix="personal", label="iCloud test", fake=fake,
        )
        assert add_resp["result"]["id"] == "icloud_personal"

        result = await broker_client.call(
            "icloud_personal",
            "list_mailboxes",
            {},
            app_sock_path=sup.app_sock_path,
        )
    finally:
        await sup.stop()
        await fake.stop()

    names = sorted(m["name"] for m in result["mailboxes"])
    assert names == ["INBOX", "Sent", "Trash"]


@pytest.mark.asyncio
async def test_call_raises_not_connected_for_unknown_integration(tmp_path: Path) -> None:
    """A resolve-NOT_FOUND from the supervisor becomes ``broker_client.IntegrationNotConnected``."""
    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        catalog={},
    )
    await sup.start()
    try:
        with pytest.raises(broker_client.IntegrationNotConnected, match="never_added"):
            await broker_client.call(
                "never_added",
                "list_mailboxes",
                {},
                app_sock_path=sup.app_sock_path,
            )
    finally:
        await sup.stop()


@pytest.mark.asyncio
async def test_call_raises_auth_failed_when_broker_returns_auth_error(
    tmp_path: Path,
) -> None:
    """If the broker responds with an ``AUTH``-coded error frame,
    ``broker_client.call()`` surfaces it as ``IntegrationAuthFailed``.

    Uses stub supervisor + stub broker UDS servers rather than the real stack —
    this is a mapping test for ``broker_client``'s error translation, and the
    real email broker's mid-session AUTH handling is broker-side work that
    lands with later verb expansion. Keeping the stub here lets us assert the
    mapping without waiting on that.
    """
    app_sock_path = tmp_path / "app.sock"
    broker_sock_path = tmp_path / "broker.sock"

    async def supervisor_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        # Canned resolve — every integration_id maps to our stub broker socket.
        if verb != "resolve":
            raise RpcError("BAD_REQUEST", f"stub supervisor only handles resolve, got {verb!r}")
        return {
            "id": args["id"],
            "socket": str(broker_sock_path),
            "write_allowed": True,
        }

    async def broker_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        raise RpcError("AUTH", "upstream rejected credentials")

    sup_server = await serve_rpc(app_sock_path, supervisor_handler)
    broker_server = await serve_rpc(broker_sock_path, broker_handler)
    async with sup_server, broker_server:
        with pytest.raises(
            broker_client.IntegrationAuthFailed,
            match="upstream rejected credentials",
        ):
            await broker_client.call(
                "gmail_personal",
                "fetch_message",
                {"mailbox": "INBOX", "uid": 1},
                app_sock_path=app_sock_path,
            )


@pytest.mark.asyncio
async def test_call_raises_write_denied_when_write_allowed_is_false(
    tmp_path: Path,
) -> None:
    """``write_allowed=False`` on the integration causes the broker to reject
    write-classified verbs with WRITE_DENIED, which ``call()`` maps to
    ``broker_client.IntegrationWriteDenied``."""
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
        await _rpc_add(
            sup.app_sock_path,
            user_suffix="personal",
            label="iCloud test",
            fake=fake,
            write_allowed=False,
        )

        # send_message is write-classified. With write_allowed=False, the
        # broker refuses locally (per its dispatcher's gate). Placeholder args —
        # the gate fires before the broker looks at the args at all.
        with pytest.raises(broker_client.IntegrationWriteDenied, match="send_message"):
            await broker_client.call(
                "icloud_personal",
                "send_message",
                {"to": "nobody@example.com", "subject": "x", "body_text": "x"},
                app_sock_path=sup.app_sock_path,
            )
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_call_send_message_lands_in_outbox_through_real_broker(
    tmp_path: Path,
) -> None:
    """End-to-end send: broker_client.call → supervisor.resolve → broker.send_message
    → SMTP AUTH + DATA against the fake → the message shows up in the outbox.

    Proves the full vertical: the SMTP client wired into a real broker
    subprocess actually sends. If this works against the fake with real TCP
    and a real Python subprocess, it'll work against iCloud / Gmail.
    """
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
        await _rpc_add(
            sup.app_sock_path,
            user_suffix="personal",
            label="iCloud test",
            fake=fake,
            write_allowed=True,
        )

        result = await broker_client.call(
            "icloud_personal",
            "send_message",
            {
                "to": ["alice@example.com"],
                "subject": "hi",
                "body": "this is the body",
            },
            app_sock_path=sup.app_sock_path,
        )
    finally:
        await sup.stop()
        await fake.stop()

    assert result["sent"] is True
    assert result["message_id"]
    assert len(fake.outbox) == 1
    captured = fake.outbox[0]
    assert captured.rcpt_to == ["alice@example.com"]
    assert b"Subject: hi" in captured.raw
    assert b"this is the body" in captured.raw


@pytest.mark.asyncio
async def test_call_move_message_relocates_through_real_broker(
    tmp_path: Path,
) -> None:
    """End-to-end move: broker_client.call → broker → UID MOVE on the fake's
    IMAP server → the source mailbox loses the message and the destination
    gains it.

    Same vertical-slice rationale as the send test — exercises the full
    stack including the broker's mode-aware SELECT switching for write verbs.
    """
    fake = FakeEmail()
    await fake.start()
    uid = fake.add_message(
        "INBOX",
        from_="alice@example.com",
        to=fake.user,
        subject="archive me",
        body="bye",
    )

    sup = Supervisor(
        vault_dir=tmp_path / "vault",
        app_sock_path=tmp_path / "app.sock",
        sockets_dir=tmp_path / "sockets",
        catalog=_test_catalog(fake),
    )
    await sup.start()
    try:
        await _rpc_add(
            sup.app_sock_path,
            user_suffix="personal",
            label="iCloud test",
            fake=fake,
            write_allowed=True,
        )

        result = await broker_client.call(
            "icloud_personal",
            "move_message",
            {"folder": "INBOX", "uid": str(uid), "dest_folder": "Trash"},
            app_sock_path=sup.app_sock_path,
        )
    finally:
        await sup.stop()
        await fake.stop()

    assert result == {"moved": True}
    assert fake.mailboxes["INBOX"].messages == []
    assert len(fake.mailboxes["Trash"].messages) == 1


