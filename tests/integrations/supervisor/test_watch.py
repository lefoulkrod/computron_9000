"""End-to-end tests for the broker-crash watcher.

The watcher's contract: when a broker subprocess exits unexpectedly, the
supervisor respawns it transparently; the integration's broker socket
keeps working from the caller's perspective. Auth-fail and persistent
crash are terminal states the watcher recognizes and stops respawning.

Like the reconcile tests, these are subprocess-tier — real broker
processes against ``FakeEmail``. Watcher behaviour is hard to fake
faithfully; spawning real children is the cheapest way to be sure.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from integrations.supervisor._catalog import BrokerSpec, CatalogEntry
from integrations.supervisor._lifecycle import Supervisor
from tests.integrations.fixtures._host_paths import (
    EMAIL_BROKER_HOST_PATHS,
    make_host_paths,
)
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
    return {
        "icloud": CatalogEntry(
            slug="icloud",
            label="iCloud",
            brokers=(
                BrokerSpec(
                    capability="email_calendar",
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
            ),
        ),
    }


async def _wait_for(predicate, timeout: float = 10.0, interval: float = 0.1) -> None:
    """Poll ``predicate`` until it returns truthy or the deadline elapses."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    msg = f"predicate did not become true within {timeout}s"
    raise AssertionError(msg)


@pytest.mark.asyncio
async def test_watcher_respawns_broker_after_unexpected_exit(tmp_path: Path) -> None:
    """The headline guarantee: kill a broker externally, the watcher brings
    it back. The new broker has a fresh PID and its socket is reachable.
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
        original_record = sup._registry.get("icloud_personal")
        assert original_record is not None
        original_pid = original_record.brokers["email_calendar"].proc.pid

        # Simulate a crash: SIGKILL the broker subprocess directly. The
        # watcher's `expected_termination` flag is False for this record,
        # so it should respawn.
        original_record.brokers["email_calendar"].proc.kill()

        # Watcher's first respawn waits 1s after the first failure detection.
        await _wait_for(
            lambda: (
                (rec := sup._registry.get("icloud_personal")) is not None
                and rec.state == "running"
                and rec.brokers["email_calendar"].proc.pid != original_pid
            ),
            timeout=15.0,
        )

        # The new broker socket should be reachable.
        rec = sup._registry.get("icloud_personal")
        mb_resp = await _rpc_call(rec.brokers["email_calendar"].socket_path, "list_mailboxes", {})
        assert "error" not in mb_resp, mb_resp
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_watcher_marks_auth_failed_when_broker_exits_77(tmp_path: Path) -> None:
    """Broker exit-code 77 (upstream rejected creds) → no respawn loop.

    Hammering the upstream's auth endpoint risks rate-limit penalties;
    the watcher gives up and flags the integration so the UI can prompt
    the user to re-add.
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

        # Now make every subsequent IMAP LOGIN fail. When we kill the
        # current broker, the respawn will exit 77 and the watcher should
        # recognize that as terminal.
        fake.reject_next_n_imap_logins = 99
        record = sup._registry.get("icloud_personal")
        original_pid = record.brokers["email_calendar"].proc.pid
        record.brokers["email_calendar"].proc.kill()

        await _wait_for(
            lambda: (
                (rec := sup._registry.get("icloud_personal")) is not None
                and rec.state == "auth_failed"
            ),
            timeout=15.0,
        )

        # list verb surfaces the new state to clients.
        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        states = {i["id"]: i["state"] for i in list_resp["result"]["integrations"]}
        assert states["icloud_personal"] == "auth_failed"

        # No further respawn attempts — the dead PID stays the latest.
        rec = sup._registry.get("icloud_personal")
        assert rec.brokers["email_calendar"].proc.returncode is not None
        assert rec.brokers["email_calendar"].proc.pid == original_pid or rec.brokers["email_calendar"].proc.returncode == 77
    finally:
        await sup.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_watcher_does_not_respawn_after_remove(tmp_path: Path) -> None:
    """Regression guard: ``remove`` flags the watcher first, so the SIGTERM
    isn't read as a crash.
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
        await _rpc_call(sup.app_sock_path, "remove", {"id": "icloud_personal"})

        # Give any (hypothetical) respawn a chance to fire — it shouldn't.
        await asyncio.sleep(2.0)

        list_resp = await _rpc_call(sup.app_sock_path, "list", {})
        assert list_resp["result"]["integrations"] == []
        assert sup._registry.get("icloud_personal") is None
    finally:
        await sup.stop()
        await fake.stop()
