"""Agent tool: get metadata for a single Google Drive file."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_size

logger = logging.getLogger(__name__)


async def get_drive_file_metadata(integration_id: str, file_id: str) -> str:
    """Get detailed metadata for one Google Drive file.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_id: The Drive file ID (from ``list_drive_files`` or ``search_drive_files``).

    Returns:
        Plain-text key-value metadata, or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "get_drive_file_metadata",
            {"file_id": file_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("get_drive_file_metadata(%r, %r) failed: %s", integration_id, file_id, exc)
        return f"Failed to get file metadata: {exc}"

    f = result.get("file", {})
    lines = [
        f"Name: {f.get('name', '(unknown)')}",
        f"ID: {f.get('id', file_id)}",
        f"Type: {f.get('mimeType', '(unknown)')}",
    ]
    if f.get("size"):
        lines.append(f"Size: {format_size(int(f['size']))}")
    if f.get("createdTime"):
        lines.append(f"Created: {f['createdTime']}")
    if f.get("modifiedTime"):
        lines.append(f"Modified: {f['modifiedTime']}")
    if f.get("webViewLink"):
        lines.append(f"Link: {f['webViewLink']}")
    return "\n".join(lines)



def build_get_drive_file_metadata_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _get_drive_file_metadata(integration_id: str, file_id: str) -> str:
        return await get_drive_file_metadata(integration_id, file_id)

    _get_drive_file_metadata.__name__ = get_drive_file_metadata.__name__
    _get_drive_file_metadata.__doc__ = (
        "Get detailed metadata for one Google Drive file — name, type, size, "
        "dates, and web link. Use the file ID from list_drive_files or "
        f"search_drive_files. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the file belongs to.\n"
        "    file_id: Drive file ID.\n\n"
        "Returns:\n"
        "    Plain text — key-value lines of file metadata, or an error notice.\n"
    )
    return _get_drive_file_metadata
