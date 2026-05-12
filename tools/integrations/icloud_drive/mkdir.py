"""Agent tool: create a directory on a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def icloud_drive_mkdir(integration_id: str, remote_path: str) -> str:
    """Create a directory (and any missing parents) on an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to use.
        remote_path: Directory path to create on the remote.

    Returns:
        A plain-text confirmation, or an error / permission notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(integration_id, "mkdir", {"remote_path": remote_path}, app_sock_path=app_sock)
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_mkdir(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to create {remote_path!r}: {exc}"
    return f"Created directory {remote_path!r}."


def build_icloud_drive_mkdir_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_mkdir(integration_id: str, remote_path: str) -> str:
        return await icloud_drive_mkdir(integration_id, remote_path)

    _icloud_drive_mkdir.__name__ = icloud_drive_mkdir.__name__
    _icloud_drive_mkdir.__doc__ = (
        "Create a directory (and any missing parents) on an iCloud Drive "
        f"integration. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to use.\n"
        "    remote_path: Directory path to create on the remote.\n\n"
        "Returns:\n"
        "    Plain text — creation confirmation.\n"
    )
    return _icloud_drive_mkdir
