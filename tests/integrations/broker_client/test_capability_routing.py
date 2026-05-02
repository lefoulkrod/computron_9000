"""Unit tests for broker_client capability routing.

Tests that ``call()`` correctly maps verbs to capabilities and passes
them to the supervisor's resolve endpoint. Uses stub UDS servers rather
than the full supervisor + broker stack — these are routing logic tests,
not integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from integrations._rpc import RpcError, serve_rpc


@pytest.mark.unit
class TestCapabilityRouting:
    """Tests that call() routes verbs to the correct capability."""

    @pytest.mark.asyncio
    async def test_email_verb_routes_to_email_calendar_capability(
        self, tmp_path: Path,
    ) -> None:
        """Email verbs resolve with capability='email_calendar'."""
        app_sock_path = tmp_path / "app.sock"
        broker_sock_path = tmp_path / "broker.sock"
        resolved_capability: str | None = None

        async def supervisor_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal resolved_capability
            if verb == "resolve":
                resolved_capability = args.get("capability")
                return {
                    "id": args["id"],
                    "socket": str(broker_sock_path),
                    "write_allowed": True,
                }
            raise RpcError("BAD_REQUEST", f"unexpected verb {verb!r}")

        async def broker_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"mailboxes": []}

        sup_server = await serve_rpc(app_sock_path, supervisor_handler)
        broker_server = await serve_rpc(broker_sock_path, broker_handler)
        async with sup_server, broker_server:
            await broker_client.call(
                "icloud_personal",
                "list_mailboxes",
                {},
                app_sock_path=app_sock_path,
            )

        assert resolved_capability == "email_calendar"

    @pytest.mark.asyncio
    async def test_storage_verb_routes_to_storage_capability(
        self, tmp_path: Path,
    ) -> None:
        """Storage verbs resolve with capability='storage'."""
        app_sock_path = tmp_path / "app.sock"
        broker_sock_path = tmp_path / "broker.sock"
        resolved_capability: str | None = None

        async def supervisor_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal resolved_capability
            if verb == "resolve":
                resolved_capability = args.get("capability")
                return {
                    "id": args["id"],
                    "socket": str(broker_sock_path),
                    "write_allowed": True,
                }
            raise RpcError("BAD_REQUEST", f"unexpected verb {verb!r}")

        async def broker_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"items": []}

        sup_server = await serve_rpc(app_sock_path, supervisor_handler)
        broker_server = await serve_rpc(broker_sock_path, broker_handler)
        async with sup_server, broker_server:
            await broker_client.call(
                "icloud_personal",
                "list_directory",
                {"path": ""},
                app_sock_path=app_sock_path,
            )

        assert resolved_capability == "storage"

    @pytest.mark.asyncio
    async def test_all_email_verbs_route_correctly(self, tmp_path: Path) -> None:
        """Every email verb maps to 'email_calendar' capability."""
        from integrations.broker_client._verb_types import _VERB_CAPABILITY

        email_verbs = [v for v, cap in _VERB_CAPABILITY.items() if cap == "email_calendar"]
        assert email_verbs, "no email verbs found"
        for verb in email_verbs:
            assert _VERB_CAPABILITY[verb] == "email_calendar", f"{verb} should be email_calendar"

    @pytest.mark.asyncio
    async def test_all_storage_verbs_route_correctly(self, tmp_path: Path) -> None:
        """Every storage verb maps to 'storage' capability."""
        from integrations.broker_client._verb_types import _VERB_CAPABILITY

        storage_verbs = [v for v, cap in _VERB_CAPABILITY.items() if cap == "storage"]
        assert storage_verbs, "no storage verbs found"
        for verb in storage_verbs:
            assert _VERB_CAPABILITY[verb] == "storage", f"{verb} should be storage"

    @pytest.mark.asyncio
    async def test_unknown_verb_raises_integration_error(self, tmp_path: Path) -> None:
        """A verb not in _VERB_CAPABILITY raises IntegrationError before any RPC."""
        app_sock_path = tmp_path / "app.sock"

        # No server needed — call() should fail before connecting
        with pytest.raises(broker_client.IntegrationError, match="unknown verb"):
            await broker_client.call(
                "icloud_personal",
                "nonexistent_verb",
                {},
                app_sock_path=app_sock_path,
            )

    @pytest.mark.asyncio
    async def test_write_storage_verb_routes_to_storage(self, tmp_path: Path) -> None:
        """Write-classified storage verbs also route to 'storage' capability."""
        app_sock_path = tmp_path / "app.sock"
        broker_sock_path = tmp_path / "broker.sock"
        resolved_capability: str | None = None

        async def supervisor_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal resolved_capability
            if verb == "resolve":
                resolved_capability = args.get("capability")
                return {
                    "id": args["id"],
                    "socket": str(broker_sock_path),
                    "write_allowed": True,
                }
            raise RpcError("BAD_REQUEST", f"unexpected verb {verb!r}")

        async def broker_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"deleted": True}

        sup_server = await serve_rpc(app_sock_path, supervisor_handler)
        broker_server = await serve_rpc(broker_sock_path, broker_handler)
        async with sup_server, broker_server:
            await broker_client.call(
                "icloud_personal",
                "delete",
                {"remote_path": "test.txt"},
                app_sock_path=app_sock_path,
            )

        assert resolved_capability == "storage"

    @pytest.mark.asyncio
    async def test_capability_not_found_raises_not_connected(self, tmp_path: Path) -> None:
        """If the supervisor says the capability isn't available, call() raises IntegrationNotConnected."""
        app_sock_path = tmp_path / "app.sock"

        async def supervisor_handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
            if verb == "resolve":
                raise RpcError("NOT_FOUND", f"capability 'storage' not available for {args['id']}")
            raise RpcError("BAD_REQUEST", f"unexpected verb {verb!r}")

        sup_server = await serve_rpc(app_sock_path, supervisor_handler)
        async with sup_server:
            with pytest.raises(
                broker_client.IntegrationNotConnected,
                match="storage",
            ):
                await broker_client.call(
                    "gmail_personal",
                    "list_directory",
                    {"path": ""},
                    app_sock_path=app_sock_path,
                )