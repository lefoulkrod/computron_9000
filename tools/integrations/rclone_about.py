"""Agent tool: get storage quota info from a connected rclone remote."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_about(integration_id: str) -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "about", {},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_about(%r) failed: %s", integration_id, exc)
        return f"Failed to get storage info for {integration_id!r}: {exc}"

    total = result.get("total_bytes", 0)
    used = result.get("used_bytes", 0)
    free = result.get("free_bytes", 0)

    def fmt(n: int) -> str:
        if n == 0:
            return "0"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(n) < 1024.0:
                return f"{n:.1f} {unit}"
            n //= 1024
        return f"{n:.1f} PB"

    total_str = fmt(total)
    used_str = fmt(used)
    free_str = fmt(free)

    return (
        f"Storage on {integration_id!r}:\n"
        f"- Total: {total_str}\n"
        f"- Used: {used_str}\n"
        f"- Free: {free_str}"
    )


def build_rclone_about_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_about(integration_id: str) -> str:
        return await rclone_about(integration_id)

    _rclone_about.__name__ = rclone_about.__name__
    _rclone_about.__doc__ = (
        "Get storage quota info (total/used/free bytes) from a connected "
        f"rclone remote. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to query.\n\n"
        "Returns:\n"
        "    A plain-text summary of storage usage."
    )
    return _rclone_about
