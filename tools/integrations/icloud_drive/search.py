"""Agent tool: search for files by name on a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)

_RESULT_CAP = 50


async def icloud_drive_search(integration_id: str, pattern: str, path: str = "") -> str:
    """Search for files by name pattern under a directory on an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to search.
        pattern: A glob pattern matched against file names (e.g. ``*.pdf``).
        path: Remote directory to search under (empty = Drive root).

    Returns:
        A plain-text list of matching paths, or a short notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "search", {"pattern": pattern, "path": path}, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_search(%r, %r, %r) failed: %s", integration_id, pattern, path, exc)
        return f"Search failed: {exc}"

    matches = result.get("matches", [])
    count = int(result.get("count", len(matches)) or 0)
    if count == 0:
        return f"No files matching {pattern!r}."
    shown = matches[:_RESULT_CAP]
    suffix = f"\n(showing first {_RESULT_CAP} of {count})" if count > _RESULT_CAP else ""
    return f"{count} match(es) for {pattern!r}:\n" + "\n".join(f"- {m}" for m in shown) + suffix


def build_icloud_drive_search_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_search(integration_id: str, pattern: str, path: str = "") -> str:
        return await icloud_drive_search(integration_id, pattern, path)

    _icloud_drive_search.__name__ = icloud_drive_search.__name__
    _icloud_drive_search.__doc__ = (
        "Search for files by name pattern under a directory on an iCloud Drive "
        f"integration. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to search.\n"
        "    pattern: A glob matched against file names (e.g. \"*.pdf\").\n"
        "    path: Remote directory to search under (empty = Drive root).\n\n"
        "Returns:\n"
        "    Plain text — one matching path per line.\n"
    )
    return _icloud_drive_search
