"""Tests for supervisor app-socket wire serialization."""

from unittest.mock import MagicMock

import pytest

from integrations.permissions import Access, Capability
from integrations.supervisor._app_sock import _record_to_dict


@pytest.mark.unit
def test_record_to_dict_includes_capabilities() -> None:
    """The list response must include a capabilities array derived from max_access."""
    record = MagicMock()
    record.meta.id = "llm_openai"
    record.meta.slug = "llm_openai"
    record.meta.label = "OpenAI"
    record.meta.permissions = {}
    record.max_access = {Capability.LLM_PROXY: Access.READ_WRITE}
    record.state = "running"
    record.broker.socket_path = "/run/cvault/llm_openai.sock"

    result = _record_to_dict(record)

    assert "capabilities" in result
    assert "llm_proxy" in result["capabilities"]


@pytest.mark.unit
def test_record_to_dict_capabilities_sorted() -> None:
    """Capabilities are sorted alphabetically for stable wire output."""
    record = MagicMock()
    record.meta.id = "icloud_alice"
    record.meta.slug = "icloud"
    record.meta.label = "iCloud"
    record.meta.permissions = {
        Capability.EMAIL: Access.READ_WRITE,
        Capability.CALENDAR: Access.READ,
    }
    record.max_access = {
        Capability.EMAIL: Access.READ_WRITE,
        Capability.CALENDAR: Access.READ_WRITE,
    }
    record.state = "running"
    record.broker.socket_path = "/run/cvault/icloud_alice.sock"

    result = _record_to_dict(record)

    assert result["capabilities"] == ["calendar", "email"]


# --- update_secrets verb --------------------------------------------------

import os
from unittest.mock import AsyncMock

from integrations._rpc import RpcError, _peer_uid_var
from integrations.supervisor._app_sock import AppSockHandler
from integrations.supervisor._catalog import CatalogEntry


def _handler(
    *,
    catalog: dict[str, CatalogEntry] | None = None,
    record_slug: str | None = "icloud_drive",
) -> tuple[AppSockHandler, MagicMock]:
    manager = MagicMock()
    manager.update_secrets = AsyncMock()
    registry = MagicMock()
    if record_slug is None:
        registry.get.return_value = None
    else:
        record = MagicMock()
        record.meta.slug = record_slug
        registry.get.return_value = record
    cat = catalog if catalog is not None else {
        "icloud_drive": CatalogEntry(
            slug="icloud_drive",
            command=["python", "-m", "x"],
            capabilities={Capability.DRIVE: Access.READ_WRITE},
            patchable_secret_keys=frozenset({"rclone_cookies"}),
        ),
    }
    return AppSockHandler(manager=manager, registry=registry, catalog=cat), manager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_rejects_non_broker_uid() -> None:
    handler, _ = _handler()
    token = _peer_uid_var.set(os.getuid() + 1)  # something other than our own
    try:
        with pytest.raises(RpcError, match="PERMISSION_DENIED|brokers only"):
            await handler.handle(
                "update_secrets",
                {"id": "icloud_drive_me", "patch": {"rclone_cookies": "v"}},
            )
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_rejects_missing_peer_uid() -> None:
    handler, _ = _handler()
    token = _peer_uid_var.set(None)
    try:
        with pytest.raises(RpcError, match="PERMISSION_DENIED"):
            await handler.handle(
                "update_secrets",
                {"id": "icloud_drive_me", "patch": {"rclone_cookies": "v"}},
            )
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_rejects_key_not_in_whitelist() -> None:
    handler, _ = _handler()
    token = _peer_uid_var.set(os.getuid())
    try:
        with pytest.raises(RpcError, match="not patchable"):
            await handler.handle(
                "update_secrets",
                {"id": "icloud_drive_me", "patch": {"password": "new"}},
            )
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_rejects_non_string_value() -> None:
    handler, _ = _handler()
    token = _peer_uid_var.set(os.getuid())
    try:
        with pytest.raises(RpcError, match="must be a string"):
            await handler.handle(
                "update_secrets",
                {"id": "icloud_drive_me", "patch": {"rclone_cookies": 42}},
            )
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_rejects_empty_patch() -> None:
    handler, _ = _handler()
    token = _peer_uid_var.set(os.getuid())
    try:
        with pytest.raises(RpcError, match="must not be empty"):
            await handler.handle("update_secrets", {"id": "icloud_drive_me", "patch": {}})
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_unknown_integration() -> None:
    handler, _ = _handler(record_slug=None)
    token = _peer_uid_var.set(os.getuid())
    try:
        with pytest.raises(RpcError, match="unknown integration"):
            await handler.handle(
                "update_secrets",
                {"id": "icloud_drive_me", "patch": {"rclone_cookies": "v"}},
            )
    finally:
        _peer_uid_var.reset(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_secrets_happy_path_forwards_to_manager() -> None:
    handler, manager = _handler()
    token = _peer_uid_var.set(os.getuid())
    try:
        result = await handler.handle(
            "update_secrets",
            {"id": "icloud_drive_me", "patch": {"rclone_cookies": "blob"}},
        )
        assert result == {"id": "icloud_drive_me"}
        manager.update_secrets.assert_awaited_once_with(
            "icloud_drive_me", {"rclone_cookies": "blob"},
        )
    finally:
        _peer_uid_var.reset(token)
