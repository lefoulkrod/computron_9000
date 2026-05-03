"""Agent tool: download or export a Google Drive file."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_size

logger = logging.getLogger(__name__)


async def export_drive_file(integration_id: str, file_id: str) -> str:
    """Download or export a Google Drive file's content.

    Google Docs, Sheets, and Slides are exported to portable formats
    (plain text, CSV, plain text respectively). Binary files are
    downloaded as-is.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_id: The Drive file ID (from ``list_drive_files`` or
            ``search_drive_files``).

    Returns:
        The on-disk path with filename and size. Use ``read_file`` or
        ``describe_image`` to work with the downloaded content.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "export_drive_file",
            {"file_id": file_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("export_drive_file(%r, %r) failed: %s", integration_id, file_id, exc)
        return f"Failed to export file: {exc}"

    filename = result.get("filename", "(unnamed)")
    size = result.get("size", 0)
    path = result.get("path", "")
    return f"Saved {filename!r} to {path} ({format_size(size)})."


def build_export_drive_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _export_drive_file(integration_id: str, file_id: str) -> str:
        return await export_drive_file(integration_id, file_id)

    _export_drive_file.__name__ = export_drive_file.__name__
    _export_drive_file.__doc__ = (
        "Download or export a Google Drive file to the local filesystem. "
        "Google Docs export as plain text, Sheets as CSV, Slides as plain "
        "text. Binary files download as-is. Returns the on-disk path — use "
        "read_file or describe_image to work with the content. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the file belongs to.\n"
        "    file_id: Drive file ID.\n\n"
        "Returns:\n"
        "    Plain text — the saved file path with filename and size.\n"
    )
    return _export_drive_file
