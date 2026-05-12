"""Agent tool: download a file from a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes

logger = logging.getLogger(__name__)


async def icloud_drive_download(
    integration_id: str, remote_path: str, local_path: str = "",
) -> str:
    """Download a file from an iCloud Drive integration to the local filesystem.

    Args:
        integration_id: Which iCloud Drive integration to read from.
        remote_path: Path to the file on the remote.
        local_path: Where to write it locally. Empty = a file named after the
            remote basename in the shared downloads directory.

    Returns:
        A plain-text confirmation including the local path written, or an error.
    """
    app_sock = load_config().integrations.app_sock_path
    args: dict[str, Any] = {"remote_path": remote_path}
    if local_path:
        args["local_path"] = local_path
    try:
        result = await broker_client.call(integration_id, "copy_from_remote", args, app_sock_path=app_sock)
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_download(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to download {remote_path!r}: {exc}"

    written = result.get("local_path", local_path or "?")
    n = int(result.get("bytes_copied", 0) or 0)
    return f"Downloaded {remote_path!r} ({human_bytes(n)}) to {written}."


def build_icloud_drive_download_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_download(
        integration_id: str, remote_path: str, local_path: str = "",
    ) -> str:
        return await icloud_drive_download(integration_id, remote_path, local_path)

    _icloud_drive_download.__name__ = icloud_drive_download.__name__
    _icloud_drive_download.__doc__ = (
        "Download a file from an iCloud Drive integration to the local "
        f"filesystem. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to read from.\n"
        "    remote_path: Path to the file on the remote.\n"
        "    local_path: Local destination (empty = downloads dir, named after the remote file).\n\n"
        "Returns:\n"
        "    Plain text — confirmation with the local path written.\n"
    )
    return _icloud_drive_download
