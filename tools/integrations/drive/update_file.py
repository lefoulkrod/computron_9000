"""Agent tool: update an existing file on Google Drive."""

from __future__ import annotations

import base64
import logging
import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def update_drive_file(
    integration_id: str,
    file_id: str,
    file_path: str | None = None,
    name: str | None = None,
) -> str:
    """Update an existing Drive file's content and/or name.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_id: Drive file ID to update.
        file_path: Path to a local file whose content replaces the existing version.
        name: New filename on Drive.

    Returns:
        Plain text — a confirmation, or a short error notice.
    """
    if file_path is None and name is None:
        return "Nothing to update — provide file_path and/or name."

    args: dict[str, Any] = {"file_id": file_id}
    if name is not None:
        args["name"] = name
    if file_path is not None:
        path = Path(file_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            return f"Cannot read file {file_path!r}: {exc}"
        args["data_b64"] = base64.b64encode(content).decode("ascii")
        args["mime_type"] = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "update_drive_file",
            args,
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "update_drive_file(%r, %r) failed: %s", integration_id, file_id, exc,
        )
        return f"Failed to update file via {integration_id!r}: {exc}"

    updated_name = result.get("file", {}).get("name", file_id)
    return f"Updated '{updated_name}' (file ID: {file_id})."


def build_update_drive_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _update_drive_file(
        integration_id: str,
        file_id: str,
        file_path: str | None = None,
        name: str | None = None,
    ) -> str:
        return await update_drive_file(integration_id, file_id, file_path, name)

    _update_drive_file.__name__ = update_drive_file.__name__
    _update_drive_file.__doc__ = (
        "Update an existing file on Google Drive. Replace its content by "
        "providing a local file_path, rename it with name, or both. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to use.\n"
        "    file_id: Drive file ID to update.\n"
        "    file_path: Optional local file whose content replaces the current version.\n"
        "    name: Optional new filename on Drive.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation, or an error notice.\n"
    )
    return _update_drive_file
