"""Agent tool: list contents of a directory on a connected rclone remote."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_list_directory(integration_id: str, path: str = "") -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "list_directory", {"path": path},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_list_directory(%r, %r) failed: %s", integration_id, path, exc)
        return f"Failed to list directory for {integration_id!r}: {exc}"

    items = result.get("items", [])
    if not items:
        return f"Directory '{path or '/'}' on {integration_id!r} is empty."

    lines = []
    for item in items:
        prefix = "[DIR]  " if item["is_dir"] else "[FILE] "
        size_str = f"  {item['size']:,} bytes" if not item["is_dir"] else ""
        lines.append(f"- {prefix}{item['name']}{size_str}  ({item['mod_time']})")

    joined = "\n".join(lines)
    return f"Contents of '{path or '/'}' on {integration_id!r}:\n{joined}"


def build_rclone_list_directory_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_list_directory(integration_id: str, path: str = "") -> str:
        return await rclone_list_directory(integration_id, path)

    _rclone_list_directory.__name__ = rclone_list_directory.__name__
    _rclone_list_directory.__doc__ = (
        "List the contents of a directory on a connected rclone remote. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to query.\n"
        "    path: Remote directory path (default: root).\n\n"
        "Returns:\n"
        "    A plain-text listing of directory contents."
    )
    return _rclone_list_directory
