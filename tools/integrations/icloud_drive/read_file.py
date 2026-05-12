"""Agent tool: read a (text) file from a connected iCloud Drive integration."""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 200_000


async def icloud_drive_read_file(
    integration_id: str, remote_path: str, max_bytes: int = _DEFAULT_MAX_BYTES,
) -> str:
    """Read the contents of a text file on an iCloud Drive integration.

    For binary files, or files larger than ``max_bytes``, use
    ``icloud_drive_download`` to fetch the file locally instead.

    Args:
        integration_id: Which iCloud Drive integration to read from.
        remote_path: Path to the file on the remote.
        max_bytes: Maximum bytes to retrieve before truncating.

    Returns:
        The file's text content (possibly truncated), or a notice for binary files.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "cat", {"remote_path": remote_path, "max_bytes": max_bytes},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_read_file(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to read {remote_path!r}: {exc}"

    raw = base64.b64decode(result.get("content", "") or "")
    total = int(result.get("size", len(raw)) or 0)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"{remote_path!r} looks like a binary file ({total} bytes). "
            "Use icloud_drive_download to fetch it locally."
        )
    if result.get("truncated"):
        return text + f"\n\n[truncated — first {max_bytes} of {total} bytes]"
    return text


def build_icloud_drive_read_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_read_file(
        integration_id: str, remote_path: str, max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> str:
        return await icloud_drive_read_file(integration_id, remote_path, max_bytes)

    _icloud_drive_read_file.__name__ = icloud_drive_read_file.__name__
    _icloud_drive_read_file.__doc__ = (
        "Read the contents of a text file on an iCloud Drive integration. For "
        "binary or large files use icloud_drive_download instead. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to read from.\n"
        "    remote_path: Path to the file on the remote.\n"
        f"    max_bytes: Maximum bytes before truncating (default {_DEFAULT_MAX_BYTES}).\n\n"
        "Returns:\n"
        "    Plain text — the file content, or a binary-file notice.\n"
    )
    return _icloud_drive_read_file
