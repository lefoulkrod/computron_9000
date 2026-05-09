"""Agent tool: move a Google Drive file to the trash."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def trash_drive_file(
    integration_id: str,
    file_id: str,
) -> str:
    """Move a Drive file to the trash.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_id: Drive file ID to trash.

    Returns:
        Plain text — a confirmation, or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "trash_drive_file",
            {"file_id": file_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "trash_drive_file(%r, %r) failed: %s", integration_id, file_id, exc,
        )
        return f"Failed to trash file via {integration_id!r}: {exc}"

    name = result.get("file", {}).get("name", file_id)
    return f"Moved '{name}' to trash (file ID: {file_id})."


def build_trash_drive_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _trash_drive_file(
        integration_id: str,
        file_id: str,
    ) -> str:
        return await trash_drive_file(integration_id, file_id)

    _trash_drive_file.__name__ = trash_drive_file.__name__
    _trash_drive_file.__doc__ = (
        "Move a Google Drive file to the trash. The file can be restored "
        "from trash within 30 days. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to use.\n"
        "    file_id: Drive file ID to trash.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation, or an error notice.\n"
    )
    return _trash_drive_file
