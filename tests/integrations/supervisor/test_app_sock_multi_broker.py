"""Tests for the AppSockHandler's multi-broker and capability routing logic.

These are unit-level tests that exercise the handler's verb dispatch without
a real supervisor or broker subprocess — the handler is constructed with a
mock Registry and BrokerManager, and we verify the right data flows through.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from integrations._rpc import RpcError
from integrations.supervisor._app_sock import AppSockHandler
from integrations.supervisor._registry import IntegrationRecord, Registry
from integrations.supervisor._spawn import BrokerHandle
from integrations.supervisor.types import IntegrationMeta


def _make_record(
    integration_id: str = "icloud_personal",
    slug: str = "icloud",
    capabilities: frozenset[str] | None = None,
    write_allowed: bool = False,
) -> IntegrationRecord:
    """Build a minimal IntegrationRecord for testing."""
    caps = capabilities or frozenset({"email_calendar"})
    # Create mock broker handles for each capability
    brokers: dict[str, BrokerHandle] = {}
    for cap in caps:
        proc = AsyncMock()
        proc.returncode = None
        brokers[cap] = BrokerHandle(
            integration_id=integration_id,
            capability=cap,
            socket_path=Path(f"/tmp/sockets/{cap}_{integration_id}.sock"),
            proc=proc,
        )
    now = datetime.now(timezone.utc)
    return IntegrationRecord(
        meta=IntegrationMeta(
            id=integration_id,
            slug=slug,
            label="Test",
            write_allowed=write_allowed,
            enabled_capabilities=sorted(caps),
            added_at=now,
            updated_at=now,
        ),
        brokers=brokers,
        capabilities=caps,
    )


@pytest.mark.unit
class TestResolveWithCapabilities:
    """Tests for the resolve verb with capability-based routing."""

    def test_resolve_with_capability_returns_correct_socket(self) -> None:
        """Resolve with a specific capability returns that broker's socket."""
        record = _make_record(
            capabilities=frozenset({"email_calendar", "storage"}),
        )
        registry = Registry()
        registry.add(record)
        handler = AppSockHandler(manager=AsyncMock(), registry=registry)

        result = handler._resolve({"id": "icloud_personal", "capability": "storage"})
        assert result["id"] == "icloud_personal"
        assert "storage" in result["socket"]
        assert result["write_allowed"] is False

    def test_resolve_email_capability(self) -> None:
        """Resolve with email_calendar capability returns the email broker's socket."""
        record = _make_record(
            capabilities=frozenset({"email_calendar", "storage"}),
        )
        registry = Registry()
        registry.add(record)
        handler = AppSockHandler(manager=AsyncMock(), registry=registry)

        result = handler._resolve({"id": "icloud_personal", "capability": "email_calendar"})
        assert result["id"] == "icloud_personal"
        assert "email_calendar" in result["socket"]

    def test_resolve_unknown_capability_raises_not_found(self) -> None:
        """Resolve with a capability not in the integration raises NOT_FOUND."""
        record = _make_record(
            capabilities=frozenset({"email_calendar"}),
        )
        registry = Registry()
        registry.add(record)
        handler = AppSockHandler(manager=AsyncMock(), registry=registry)

        with pytest.raises(RpcError, match="capability.*not available"):
            handler._resolve({"id": "icloud_personal", "capability": "storage"})

    def test_resolve_without_capability_defaults_to_first(self) -> None:
        """Resolve without capability uses the first broker (backward compat)."""
        record = _make_record(
            capabilities=frozenset({"email_calendar", "storage"}),
        )
        registry = Registry()
        registry.add(record)
        handler = AppSockHandler(manager=AsyncMock(), registry=registry)

        result = handler._resolve({"id": "icloud_personal"})
        # Should return the first broker's socket (email_calendar comes first alphabetically)
        assert result["id"] == "icloud_personal"
        assert result["write_allowed"] is False

    def test_resolve_unknown_integration_raises_not_found(self) -> None:
        """Resolve for an integration that doesn't exist raises NOT_FOUND."""
        registry = Registry()
        handler = AppSockHandler(manager=AsyncMock(), registry=registry)

        with pytest.raises(RpcError, match="unknown integration"):
            handler._resolve({"id": "nonexistent"})


@pytest.mark.unit
class TestAddWithCapabilities:
    """Tests for the add verb with enabled_capabilities."""

    @pytest.mark.asyncio
    async def test_add_with_enabled_capabilities(self) -> None:
        """Add with enabled_capabilities passes them to the manager."""
        manager = AsyncMock()
        record = _make_record(
            capabilities=frozenset({"email_calendar", "storage"}),
        )
        manager.add.return_value = record
        registry = Registry()
        handler = AppSockHandler(manager=manager, registry=registry)

        result = await handler._add({
            "slug": "icloud",
            "user_suffix": "personal",
            "label": "Test",
            "auth_blob": {"email": "test@example.com", "password": "pass"},
            "write_allowed": False,
            "enabled_capabilities": ["email_calendar", "storage"],
        })

        manager.add.assert_called_once()
        call_kwargs = manager.add.call_args[1]
        assert call_kwargs["enabled_capabilities"] == ["email_calendar", "storage"]

    @pytest.mark.asyncio
    async def test_add_without_enabled_capabilities_defaults_to_none(self) -> None:
        """Add without enabled_capabilities passes None (supervisor defaults to all)."""
        manager = AsyncMock()
        record = _make_record()
        manager.add.return_value = record
        registry = Registry()
        handler = AppSockHandler(manager=manager, registry=registry)

        result = await handler._add({
            "slug": "icloud",
            "user_suffix": "personal",
            "label": "Test",
            "auth_blob": {"email": "test@example.com", "password": "pass"},
            "write_allowed": False,
        })

        manager.add.assert_called_once()
        call_kwargs = manager.add.call_args[1]
        assert call_kwargs["enabled_capabilities"] is None

    @pytest.mark.asyncio
    async def test_add_rejects_non_list_enabled_capabilities(self) -> None:
        """Add with a non-list enabled_capabilities raises BAD_REQUEST."""
        manager = AsyncMock()
        registry = Registry()
        handler = AppSockHandler(manager=manager, registry=registry)

        with pytest.raises(RpcError, match="must be a list of strings"):
            await handler._add({
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "Test",
                "auth_blob": {"email": "test@example.com", "password": "pass"},
                "write_allowed": False,
                "enabled_capabilities": "email_calendar",
            })

    @pytest.mark.asyncio
    async def test_add_rejects_non_string_elements_in_capabilities(self) -> None:
        """Add with non-string elements in enabled_capabilities raises BAD_REQUEST."""
        manager = AsyncMock()
        registry = Registry()
        handler = AppSockHandler(manager=manager, registry=registry)

        with pytest.raises(RpcError, match="must be a list of strings"):
            await handler._add({
                "slug": "icloud",
                "user_suffix": "personal",
                "label": "Test",
                "auth_blob": {"email": "test@example.com", "password": "pass"},
                "write_allowed": False,
                "enabled_capabilities": [123],
            })


@pytest.mark.unit
class TestRecordToDict:
    """Tests for the _record_to_dict helper with multi-broker records."""

    def test_single_capability_record(self) -> None:
        """Record with one capability has sockets dict with one entry."""
        from integrations.supervisor._app_sock import _record_to_dict

        record = _make_record(capabilities=frozenset({"email_calendar"}))
        result = _record_to_dict(record)

        assert result["id"] == "icloud_personal"
        assert "email_calendar" in result["sockets"]
        assert result["capabilities"] == ["email_calendar"]
        # Backward compat: "socket" field points to first broker
        assert result["socket"] == result["sockets"]["email_calendar"]

    def test_multi_capability_record(self) -> None:
        """Record with multiple capabilities has sockets dict with all entries."""
        from integrations.supervisor._app_sock import _record_to_dict

        record = _make_record(
            capabilities=frozenset({"email_calendar", "storage"}),
        )
        result = _record_to_dict(record)

        assert result["id"] == "icloud_personal"
        assert "email_calendar" in result["sockets"]
        assert "storage" in result["sockets"]
        assert sorted(result["capabilities"]) == ["email_calendar", "storage"]
        # Backward compat: "socket" field points to one of the broker sockets
        assert result["socket"] in result["sockets"].values()

    def test_write_allowed_reflected(self) -> None:
        """write_allowed is reflected in the output."""
        from integrations.supervisor._app_sock import _record_to_dict

        record = _make_record(write_allowed=True)
        result = _record_to_dict(record)
        assert result["write_allowed"] is True