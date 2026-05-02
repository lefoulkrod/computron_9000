"""Agent tool: get size info for a path on a connected rclone remote."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_size(integration_id: str, path: str = "") -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "size", {"path": path},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_size(%r, %r) failed: %s", integration_id, path, exc)
        return f"Failed to get size info for {integration_id!r}: {exc}"

    count = result.get("count", 0)
    total_bytes = result.get("bytes", 0)

    def fmt(n: int) -> str:
        if n == 0:
            return "0"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(n) < 1024.0:
                return f"{n:.1f} {unit}"
            n //= 1024
        return f"{n:.1f} PB"

    return (
        f"Size of '{path or '/'}' on {integration_id!r}:\n"
        f"- Files: {count:,}\n"
        f"- Total: {fmt(total_bytes)}"
    )


def build_rclone_size_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_size(integration_id: str, path: str = "") -> str:
        return await rclone_size(integration_id, path)

    _rclone_size.__name__ = rclone_size.__name__
    _rclone_size.__doc__ = (
        "Get the number of files and total bytes for a path on a connected rclone remote. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to query.\n"
        "    path: Remote path to check (default: root).\n\n"
        "Returns:\n"
        "    A plain-text summary of file count and total size."
    )
    return _rclone_size
