"""Agent tool: list files in a Google Drive folder."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_file

logger = logging.getLogger(__name__)


async def list_drive_files(
    integration_id: str,
    folder_id: str = "root",
    limit: int = 50,
) -> str:
    """List files in a Google Drive folder.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        folder_id: Drive folder ID to list (default ``"root"`` for My Drive top level).
        limit: Maximum files to return (1–100, default 50).

    Returns:
        Plain-text listing of files, or a short error/empty notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_drive_files",
            {"folder_id": folder_id, "limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_drive_files(%r, %r) failed: %s", integration_id, folder_id, exc)
        return f"Failed to list Drive files: {exc}"

    files = result.get("files", [])
    if not files:
        return "No files in this folder."
    lines = [format_file(f) for f in files]
    return f"Drive files ({len(lines)}):\n" + "\n".join(lines)


def build_list_drive_files_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_drive_files(
        integration_id: str,
        folder_id: str = "root",
        limit: int = 50,
    ) -> str:
        return await list_drive_files(integration_id, folder_id, limit)

    _list_drive_files.__name__ = list_drive_files.__name__
    _list_drive_files.__doc__ = (
        "List files in a Google Drive folder. Returns one file per line with "
        "the file ID in brackets. Use the file ID with other Drive tools. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        '    integration_id: Which integration to read from.\n'
        '    folder_id: Drive folder ID (default "root" for top-level).\n'
        "    limit: Maximum files to return (1-100, default 50).\n\n"
        "Returns:\n"
        "    Plain text — one file per line, formatted as "
        '"- [file_id] filename  —  type (size)".\n'
    )
    return _list_drive_files
