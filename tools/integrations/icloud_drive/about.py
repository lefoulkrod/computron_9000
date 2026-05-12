"""Agent tool: report storage quota for a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes

logger = logging.getLogger(__name__)


async def icloud_drive_about(integration_id: str) -> str:
    """Report total / used / free storage for an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to query.

    Returns:
        A plain-text summary of storage usage.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(integration_id, "about", {}, app_sock_path=app_sock)
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_about(%r) failed: %s", integration_id, exc)
        return f"Failed to read storage info: {exc}"

    return (
        "Storage:\n"
        f"- Total: {human_bytes(int(result.get('total_bytes', 0) or 0))}\n"
        f"- Used:  {human_bytes(int(result.get('used_bytes', 0) or 0))}\n"
        f"- Free:  {human_bytes(int(result.get('free_bytes', 0) or 0))}"
    )


def build_icloud_drive_about_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_about(integration_id: str) -> str:
        return await icloud_drive_about(integration_id)

    _icloud_drive_about.__name__ = icloud_drive_about.__name__
    _icloud_drive_about.__doc__ = (
        "Report total / used / free storage for an iCloud Drive integration. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to query.\n\n"
        "Returns:\n"
        "    Plain text — a three-line storage summary.\n"
    )
    return _icloud_drive_about
