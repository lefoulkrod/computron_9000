"""Agent tool: report file count and total bytes for a path on an iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes

logger = logging.getLogger(__name__)


async def icloud_drive_size(integration_id: str, path: str = "") -> str:
    """Report the number of files and total bytes under a path on an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to query.
        path: Remote path to measure (empty = whole Drive).

    Returns:
        A plain-text summary of file count and total size.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "size", {"path": path}, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_size(%r, %r) failed: %s", integration_id, path, exc)
        return f"Failed to measure {path or '/'!r}: {exc}"

    count = int(result.get("count", 0) or 0)
    total = int(result.get("bytes", 0) or 0)
    return f"{path or '/'}: {count} file(s), {human_bytes(total)} total."


def build_icloud_drive_size_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_size(integration_id: str, path: str = "") -> str:
        return await icloud_drive_size(integration_id, path)

    _icloud_drive_size.__name__ = icloud_drive_size.__name__
    _icloud_drive_size.__doc__ = (
        "Report the number of files and total bytes under a path on an iCloud "
        f"Drive integration. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to query.\n"
        "    path: Remote path to measure (empty = whole Drive).\n\n"
        "Returns:\n"
        "    Plain text — a one-line count + size summary.\n"
    )
    return _icloud_drive_size
