"""In-memory record of which integrations are currently available.

Tracks ``id -> slug`` for every active integration. Call
:func:`refresh_registered_integrations` to resync from the source of truth;
``mark_added`` / ``mark_removed`` apply individual mutations in between.
"""

from __future__ import annotations

import asyncio
import json
import logging

from config import load_config

logger = logging.getLogger(__name__)

_registered: dict[str, str] = {}


def mark_added(integration_id: str, slug: str) -> None:
    """Record that an integration has been successfully added."""
    _registered[integration_id] = slug


def mark_removed(integration_id: str) -> None:
    """Record that an integration has been removed. No-op if unknown."""
    _registered.pop(integration_id, None)


def has_any_integration() -> bool:
    """True iff at least one integration is registered."""
    return bool(_registered)


def registered_integrations() -> frozenset[str]:
    """Snapshot of the slugs of currently registered integrations."""
    return frozenset(_registered.values())


def registered_ids() -> frozenset[str]:
    """Snapshot of the current registered integration IDs."""
    return frozenset(_registered.keys())


async def refresh_registered_integrations() -> None:
    """Resync the in-memory list of integrations from the source of truth.

    Logs and returns silently on transport errors; the cache stays as-is
    until the next successful call.
    """
    sock_path = load_config().integrations.app_sock_path
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning(
            "integrations source not reachable at %s (%s); "
            "integration tools hidden until next successful refresh",
            sock_path, exc,
        )
        return

    try:
        body = json.dumps({"id": 1, "verb": "list", "args": {}}).encode("utf-8")
        writer.write(len(body).to_bytes(4, "big") + body)
        await writer.drain()
        length = int.from_bytes(await reader.readexactly(4), "big")
        resp = json.loads(await reader.readexactly(length))
    finally:
        writer.close()
        await writer.wait_closed()

    if "error" in resp:
        logger.warning("list error from integrations source: %s", resp["error"])
        return

    _registered.clear()
    for entry in resp.get("result", {}).get("integrations", []):
        integration_id = entry.get("id")
        slug = entry.get("slug")
        if isinstance(integration_id, str) and isinstance(slug, str):
            _registered[integration_id] = slug

    logger.info("loaded %d registered integration(s)", len(_registered))
