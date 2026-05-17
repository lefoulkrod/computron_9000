"""Agent tool: list entries in a Drive folder."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_entry

logger = logging.getLogger(__name__)


async def drive_list(
    integration_id: str,
    handle: str = "",
    pattern: str = "",
    limit: int = 50,
) -> str:
    """List entries in a Drive folder, optionally filtered by name substring.

    Args:
        integration_id: Which Drive integration to query.
        handle: Folder handle. Empty = the Drive root. For Google integrations
            handles look like ``id:<file_id>``; for path-addressed integrations
            (iCloud Drive) they look like ``Documents/Reports``.
        pattern: If non-empty, return only direct-children entries whose name
            contains this substring. If empty, list all direct children.
        limit: Maximum entries to return (default 50).

    Returns:
        Plain text — one entry per line, with the entry's handle in brackets
        so the agent can pass it back to other tools.
    """
    app_sock = load_config().integrations.app_sock_path
    args: dict[str, Any] = {"handle": handle, "limit": limit}
    if pattern:
        args["pattern"] = pattern
    try:
        result = await broker_client.call(
            integration_id, "drive_list", args, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "drive_list(%r, %r, pattern=%r) failed: %s",
            integration_id, handle, pattern, exc,
        )
        return f"Failed to list Drive entries: {exc}"

    entries = result.get("entries", [])
    if not entries:
        return "No matching entries." if pattern else "This folder is empty."
    lines = [format_entry(e) for e in entries]
    header = (
        f"{len(lines)} match(es) for {pattern!r}"
        if pattern else f"{len(lines)} entr{'y' if len(lines) == 1 else 'ies'}"
    )
    return header + ":\n" + "\n".join(lines)


def build_drive_list_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_list(
        integration_id: str, handle: str = "", pattern: str = "", limit: int = 50,
    ) -> str:
        return await drive_list(integration_id, handle, pattern, limit)

    _drive_list.__name__ = drive_list.__name__
    _drive_list.__doc__ = (
        "List entries in a Drive folder, optionally filtered by name "
        f"substring. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to query.\n"
        "    handle: Folder handle (empty = root). Use the handle string from\n"
        "        a previous drive_list result; the format varies by backend\n"
        "        (Google uses 'id:<file_id>', path-based remotes use a slash\n"
        "        path).\n"
        "    pattern: If non-empty, return only direct-children entries whose\n"
        "        name contains this substring.\n"
        "    limit: Maximum entries to return (default 50).\n\n"
        "Returns:\n"
        "    Plain text — one entry per line; each line ends with [handle] so\n"
        "    you can pass the handle to other drive_* tools.\n"
    )
    return _drive_list
