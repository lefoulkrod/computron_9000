"""Agent tool: upload a local file to a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes

logger = logging.getLogger(__name__)


async def icloud_drive_upload(integration_id: str, local_path: str, remote_path: str) -> str:
    """Upload a local file to an iCloud Drive integration.

    Args:
        integration_id: Which iCloud Drive integration to write to.
        local_path: Path to the local file to upload.
        remote_path: Destination path on the remote (including the file name).

    Returns:
        A plain-text confirmation, or an error / permission notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "copy_to_remote",
            {"local_path": local_path, "remote_path": remote_path},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_upload(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to upload to {remote_path!r}: {exc}"

    n = int(result.get("bytes_copied", 0) or 0)
    return f"Uploaded {local_path!r} ({human_bytes(n)}) to {result.get('remote_path', remote_path)!r}."


def build_icloud_drive_upload_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_upload(integration_id: str, local_path: str, remote_path: str) -> str:
        return await icloud_drive_upload(integration_id, local_path, remote_path)

    _icloud_drive_upload.__name__ = icloud_drive_upload.__name__
    _icloud_drive_upload.__doc__ = (
        "Upload a local file to an iCloud Drive integration. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to write to.\n"
        "    local_path: Path to the local file to upload.\n"
        "    remote_path: Destination path on the remote (including the file name).\n\n"
        "Returns:\n"
        "    Plain text — upload confirmation.\n"
    )
    return _icloud_drive_upload
