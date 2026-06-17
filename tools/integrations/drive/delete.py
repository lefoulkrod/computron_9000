"""Agent tool: delete an entry in a Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def drive_delete(integration_id: str, handle: str) -> str:
    """Delete a file or folder in a Drive integration.

    On Google Drive this moves the file to the trash (recoverable); on
    path-addressed remotes (iCloud Drive via rclone) it's a regular delete.
    Deleting a folder also removes its contents.

    Args:
        integration_id: Which Drive integration to use.
        handle: Handle of the entry to delete.

    Returns:
        Plain text — delete confirmation.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(
            integration_id, "drive_delete", {"handle": handle}, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_delete(%r, %r) failed: %s", integration_id, handle, exc)
        return f"Failed to delete {handle!r}: {exc}"
    return f"Deleted {handle!r}."


def build_drive_delete_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_delete(integration_id: str, handle: str) -> str:
        return await drive_delete(integration_id, handle)

    _drive_delete.__name__ = drive_delete.__name__
    _drive_delete.__doc__ = (
        "Delete a file or folder in a Drive integration. On Google Drive this "
        "moves the file to the trash; on rclone-backed remotes it deletes "
        f"directly. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to use.\n"
        "    handle: Handle of the entry to delete.\n\n"
        "Returns:\n"
        "    Plain text — delete confirmation.\n"
    )
    return _drive_delete
