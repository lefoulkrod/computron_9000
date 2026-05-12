"""Agent tool: list a directory on a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes

logger = logging.getLogger(__name__)


async def icloud_drive_list_directory(integration_id: str, path: str = "") -> str:
    """List the contents of a directory on an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to query.
        path: Remote directory path (empty string = the Drive root).

    Returns:
        A plain-text listing — one entry per line — or a short notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "list_directory", {"path": path}, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_list_directory(%r, %r) failed: %s", integration_id, path, exc)
        return f"Failed to list {path or '/'!r}: {exc}"

    items = result.get("items", [])
    if not items:
        return f"{path or '/'} is empty."
    lines = []
    for item in items:
        if item.get("is_dir"):
            lines.append(f"- [dir]  {item.get('name', '?')}/")
        else:
            lines.append(f"- [file] {item.get('name', '?')}  ({human_bytes(int(item.get('size', 0) or 0))})")
    return f"Contents of {path or '/'} ({len(lines)}):\n" + "\n".join(lines)


def build_icloud_drive_list_directory_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_list_directory(integration_id: str, path: str = "") -> str:
        return await icloud_drive_list_directory(integration_id, path)

    _icloud_drive_list_directory.__name__ = icloud_drive_list_directory.__name__
    _icloud_drive_list_directory.__doc__ = (
        "List the contents of a directory on an iCloud Drive integration. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to query.\n"
        "    path: Remote directory path (empty = Drive root).\n\n"
        "Returns:\n"
        "    Plain text — one entry per line, directories marked [dir].\n"
    )
    return _icloud_drive_list_directory
