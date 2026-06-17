"""Agent tool: upload a local file to a Drive integration."""

from __future__ import annotations

import base64
import logging
import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import human_bytes

logger = logging.getLogger(__name__)


async def drive_upload(
    integration_id: str,
    local_path: str,
    parent_handle: str = "",
    name: str = "",
) -> str:
    """Upload a local file to a Drive integration.

    The tool reads the file's bytes, base64-encodes them, and sends them to
    the broker — the broker does the upload itself, so no shared filesystem
    is required between the agent and the broker process.

    Args:
        integration_id: Which Drive integration to write to.
        local_path: Path to the local file to upload.
        parent_handle: Destination folder handle (empty = root).
        name: Optional destination filename. Defaults to the basename of
            ``local_path``.

    Returns:
        Plain text — upload confirmation.
    """
    source = Path(local_path)
    try:
        content = source.read_bytes()
    except FileNotFoundError:
        return f"Local file not found: {local_path!r}."
    except OSError as exc:
        return f"Couldn't read {local_path!r}: {exc}"

    upload_name = name or source.name
    mime_type, _ = mimetypes.guess_type(upload_name)
    if not mime_type:
        mime_type = "application/octet-stream"

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "drive_upload",
            {
                "parent_handle": parent_handle,
                "name": upload_name,
                "data_b64": base64.b64encode(content).decode("ascii"),
                "mime_type": mime_type,
            },
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_upload(%r, %r) failed: %s", integration_id, upload_name, exc)
        return f"Failed to upload {upload_name!r}: {exc}"

    entry = result.get("entry", {})
    handle = entry.get("handle", "?")
    return f"Uploaded {upload_name!r} ({human_bytes(len(content))}). Handle: {handle}"


def build_drive_upload_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_upload(
        integration_id: str, local_path: str, parent_handle: str = "", name: str = "",
    ) -> str:
        return await drive_upload(integration_id, local_path, parent_handle, name)

    _drive_upload.__name__ = drive_upload.__name__
    _drive_upload.__doc__ = (
        "Upload a local file to a Drive integration. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to write to.\n"
        "    local_path: Path to the local file to upload.\n"
        "    parent_handle: Destination folder handle (empty = root).\n"
        "    name: Optional destination filename (default: basename of local_path).\n\n"
        "Returns:\n"
        "    Plain text — upload confirmation with the new entry's handle.\n"
    )
    return _drive_upload
