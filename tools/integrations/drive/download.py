"""Agent tool: download a file from a Drive integration to the local filesystem."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import human_bytes

logger = logging.getLogger(__name__)


async def drive_download(integration_id: str, handle: str) -> str:
    """Download a file from a Drive integration to the local filesystem.

    For Google-format documents (Docs/Sheets/Slides) the broker exports as
    plain text or CSV so the result can be read with the standard read_file
    tool. Other files are downloaded as-is.

    Args:
        integration_id: Which Drive integration to read from.
        handle: File handle (from a prior ``drive_list`` result).

    Returns:
        Plain text — a one-line confirmation including the local path written.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "drive_download", {"handle": handle}, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_download(%r, %r) failed: %s", integration_id, handle, exc)
        return f"Failed to download {handle!r}: {exc}"

    local_path = result.get("local_path", "?")
    filename = result.get("filename", "?")
    mime = result.get("mime_type") or ""
    size = int(result.get("size", 0) or 0)
    mime_str = f" ({mime})" if mime else ""
    return f"Downloaded {filename!r}{mime_str}, {human_bytes(size)}, to {local_path}."


def build_drive_download_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_download(integration_id: str, handle: str) -> str:
        return await drive_download(integration_id, handle)

    _drive_download.__name__ = drive_download.__name__
    _drive_download.__doc__ = (
        "Download a file from a Drive integration to the local filesystem. "
        "Google-format documents are exported to plain text (or CSV for sheets) "
        "so the result can be read with read_file. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to read from.\n"
        "    handle: File handle from a prior drive_list result.\n\n"
        "Returns:\n"
        "    Plain text — confirmation with the local path written.\n"
    )
    return _drive_download
