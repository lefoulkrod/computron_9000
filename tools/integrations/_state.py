"""In-memory record of which integrations are currently available.

Tracks one :class:`RegisteredIntegration` per active integration, keyed by
ID. The cache loads on first read: :func:`registered_integrations` calls
:func:`_ensure_loaded`, which kicks off the supervisor probe on the first
call and awaits its completion (with a short timeout) before returning.
Subsequent calls hit a warm cache. ``mark_added`` / ``mark_removed`` apply
individual mutations in between.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable

from config import load_config
from tools.integrations.types import RegisteredIntegration

logger = logging.getLogger(__name__)

_LOAD_WAIT_SECONDS = 5.0

_registered: dict[str, RegisteredIntegration] = {}
_load_future: asyncio.Future[None] | None = None


def cache_loaded() -> bool:
    """True iff the most recent load attempt succeeded.

    Failure paths in :func:`refresh_registered_integrations` clear the
    in-flight future, so this only returns True after the cache reflects
    the supervisor's state at least once. An empty cache after a successful
    load (no integrations registered) still counts as loaded.
    """
    return _load_future is not None and _load_future.done()


def mark_added(
    integration_id: str,
    slug: str,
    capabilities: Iterable[str],
    state: str = "running",
    write_allowed: bool = False,
) -> None:
    """Record that an integration has been successfully added.

    Filters non-string entries out of ``capabilities`` so a malformed RPC
    response can't poison the cache with junk that ``in`` checks would
    silently miss against the documented ``str`` capability vocabulary.
    """
    _registered[integration_id] = RegisteredIntegration(
        id=integration_id,
        slug=slug,
        capabilities=frozenset(c for c in (capabilities or ()) if isinstance(c, str)),
        state=state if isinstance(state, str) else "running",
        write_allowed=bool(write_allowed),
    )


def mark_removed(integration_id: str) -> None:
    """Record that an integration has been removed. No-op if unknown."""
    _registered.pop(integration_id, None)


async def registered_integrations() -> dict[str, RegisteredIntegration]:
    """Snapshot of currently registered integrations, keyed by ID.

    Returns a fresh dict — callers can iterate, filter by capability, or
    look up a specific record without coordinating with internal state.
    """
    await _ensure_loaded()
    return dict(_registered)


async def _ensure_loaded() -> None:
    """Load the cache on first call; share the in-flight future thereafter.

    Times out silently after ``_LOAD_WAIT_SECONDS`` so a slow or unreachable
    supervisor doesn't hang the agent — that turn just sees an empty cache,
    and the next read retries the same future (or re-triggers a load if it
    finished and was reset).
    """
    global _load_future
    if _load_future is None:
        _load_future = asyncio.ensure_future(refresh_registered_integrations())
    if _load_future.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(_load_future), timeout=_LOAD_WAIT_SECONDS)
    except TimeoutError:
        logger.warning(
            "integrations cache still loading after %.1fs; tools may be hidden this turn",
            _LOAD_WAIT_SECONDS,
        )


async def refresh_registered_integrations() -> None:
    """Resync the in-memory list of integrations from the source of truth.

    On transport failure or a supervisor-side error, clears the in-flight
    load future so the *next* caller re-triggers — protects against the
    startup race where the app's first load fires before the supervisor
    has bound its socket.
    """
    global _load_future
    sock_path = load_config().integrations.app_sock_path
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning(
            "integrations source not reachable at %s (%s); "
            "integration tools hidden until next successful refresh",
            sock_path, exc,
        )
        _load_future = None
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
        _load_future = None
        return

    _registered.clear()
    for entry in resp.get("result", {}).get("integrations", []):
        integration_id = entry.get("id")
        slug = entry.get("slug")
        if not (isinstance(integration_id, str) and isinstance(slug, str)):
            continue
        mark_added(
            integration_id,
            slug,
            entry.get("capabilities") or (),
            entry.get("state") or "running",
            bool(entry.get("write_allowed", False)),
        )

    logger.info("loaded %d registered integration(s)", len(_registered))
