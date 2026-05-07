"""Agent tool: create a folder on Google Drive."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def create_drive_folder(
    integration_id: str,
    name: str,
    parent_id: str | None = None,
) -> str:
    """Create a folder on Google Drive.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        name: Name for the new folder.
        parent_id: Optional parent folder ID (defaults to My Drive root).

    Returns:
        Plain text — a confirmation with the folder ID, or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "create_drive_folder",
            {"name": name, "parent_id": parent_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "create_drive_folder(%r, %r) failed: %s", integration_id, name, exc,
        )
        return f"Failed to create folder via {integration_id!r}: {exc}"

    folder_id = result.get("file", {}).get("id", "")
    return f"Created folder '{name}' (folder ID: {folder_id})."


def build_create_drive_folder_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _create_drive_folder(
        integration_id: str,
        name: str,
        parent_id: str | None = None,
    ) -> str:
        return await create_drive_folder(integration_id, name, parent_id)

    _create_drive_folder.__name__ = create_drive_folder.__name__
    _create_drive_folder.__doc__ = (
        "Create a new folder on Google Drive. Use the returned folder ID "
        "as the parent_id when uploading files into it. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to use.\n"
        "    name: Name for the new folder.\n"
        "    parent_id: Optional parent folder ID (defaults to My Drive root).\n\n"
        "Returns:\n"
        "    Plain text — a confirmation with the folder ID, or an error notice.\n"
    )
    return _create_drive_folder
