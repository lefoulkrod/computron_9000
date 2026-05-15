"""Agent tool: upload a file to Google Drive."""

from __future__ import annotations

import base64
import logging
import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_size

logger = logging.getLogger(__name__)


async def upload_drive_file(
    integration_id: str,
    file_path: str,
    name: str | None = None,
    parent_id: str | None = None,
) -> str:
    """Upload a local file to Google Drive.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_path: Path to the local file to upload.
        name: Filename on Drive (defaults to the local file's basename).
        parent_id: Optional Drive folder ID to upload into.

    Returns:
        Plain text — a confirmation with file ID and size, or a short error notice.
    """
    path = Path(file_path)
    try:
        content = path.read_bytes()
    except OSError as exc:
        return f"Cannot read file {file_path!r}: {exc}"

    upload_name = name or path.name
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "upload_drive_file",
            {
                "name": upload_name,
                "data_b64": base64.b64encode(content).decode("ascii"),
                "mime_type": mime_type,
                "parent_id": parent_id,
            },
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "upload_drive_file(%r, %r) failed: %s", integration_id, file_path, exc,
        )
        return f"Failed to upload via {integration_id!r}: {exc}"

    file_id = result.get("file", {}).get("id", "")
    size_str = format_size(len(content))
    return f"Uploaded '{upload_name}' to Drive (file ID: {file_id}, {size_str})."


def build_upload_drive_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _upload_drive_file(
        integration_id: str,
        file_path: str,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> str:
        return await upload_drive_file(integration_id, file_path, name, parent_id)

    _upload_drive_file.__name__ = upload_drive_file.__name__
    _upload_drive_file.__doc__ = (
        "Upload a local file to Google Drive. The file is read from the local "
        "filesystem, so you must have created or downloaded it first. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to upload through.\n"
        "    file_path: Path to the local file.\n"
        "    name: Filename on Drive (defaults to the local file's basename).\n"
        "    parent_id: Optional Drive folder ID to upload into.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation with file ID and size, or an error notice.\n"
    )
    return _upload_drive_file
