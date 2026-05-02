"""Agent tool: search for files on a connected rclone remote."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_search(integration_id: str, pattern: str, path: str = "") -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "search", {"pattern": pattern, "path": path},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_search(%r, %r, %r) failed: %s", integration_id, pattern, path, exc)
        return f"Failed to search {integration_id!r}: {exc}"

    matches = result.get("matches", [])
    count = result.get("count", 0)
    if count == 0:
        return f"No matches found for {pattern!r} on {integration_id!r}."
    lines = [f"  {m}" for m in matches[:50]]  # Cap at 50 results
    truncated = " (showing first 50)" if count > 50 else ""
    header = f"Found {count} match(es) for {pattern!r} on {integration_id!r}{truncated}:\n"
    return header + "\n".join(lines)


def build_rclone_search_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_search(integration_id: str, pattern: str, path: str = "") -> str:
        return await rclone_search(integration_id, pattern, path)

    _rclone_search.__name__ = rclone_search.__name__
    _rclone_search.__doc__ = (
        "Search for files by name pattern on a connected rclone remote. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to search.\n"
        "    pattern: Search pattern (glob or substring, depending on the remote).\n"
        "    path: Remote directory to search in (default: root).\n\n"
        "Returns:\n"
        "    A plain-text list of matching file paths."
    )
    return _rclone_search
