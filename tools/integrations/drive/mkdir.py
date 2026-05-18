"""Agent tool: create a folder in a Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def drive_mkdir(integration_id: str, name: str, parent_handle: str = "") -> str:
    """Create a folder in a Drive integration.

    Args:
        integration_id: Which Drive integration to use.
        name: Name for the new folder.
        parent_handle: Handle of the parent folder (empty = root).

    Returns:
        Plain text — creation confirmation with the new folder's handle.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "drive_mkdir",
            {"parent_handle": parent_handle, "name": name},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_mkdir(%r, %r) failed: %s", integration_id, name, exc)
        return f"Failed to create folder {name!r}: {exc}"

    handle = result.get("entry", {}).get("handle", "?")
    return f"Created folder {name!r}. Handle: {handle}"


def build_drive_mkdir_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_mkdir(integration_id: str, name: str, parent_handle: str = "") -> str:
        return await drive_mkdir(integration_id, name, parent_handle)

    _drive_mkdir.__name__ = drive_mkdir.__name__
    _drive_mkdir.__doc__ = (
        "Create a folder in a Drive integration. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to use.\n"
        "    name: Name for the new folder.\n"
        "    parent_handle: Handle of the parent folder (empty = root).\n\n"
        "Returns:\n"
        "    Plain text — creation confirmation with the new folder's handle.\n"
    )
    return _drive_mkdir
