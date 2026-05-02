"""Agent tool: read file contents from a connected rclone remote."""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_cat(integration_id: str, remote_path: str, max_bytes: int = 1_000_000) -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "cat", {"remote_path": remote_path, "max_bytes": max_bytes},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_cat(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to read file from {integration_id!r}: {exc}"

    content_b64 = result.get("content", "")
    truncated = result.get("truncated", False)
    total_size = result.get("size", 0)

    try:
        raw_bytes = base64.b64decode(content_b64)
        # Try to decode as UTF-8 text
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return f"Binary file ({total_size:,} bytes) on {integration_id!r} at {remote_path!r}. Use rclone_copy to download it."

        suffix = f"\n\n[Truncated — showing first {max_bytes:,} of {total_size:,} bytes]" if truncated else ""
        return text + suffix
    except Exception:
        return f"Failed to decode file from {integration_id!r} at {remote_path!r}."


def build_rclone_cat_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_cat(integration_id: str, remote_path: str, max_bytes: int = 1_000_000) -> str:
        return await rclone_cat(integration_id, remote_path, max_bytes)

    _rclone_cat.__name__ = rclone_cat.__name__
    _rclone_cat.__doc__ = (
        "Read the contents of a file on a connected rclone remote. "
        "Returns text content directly; for binary files, use rclone_copy to download. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to use.\n"
        "    remote_path: Path to the file on the remote.\n"
        "    max_bytes: Maximum bytes to read (default 1000000).\n\n"
        "Returns:\n"
        "    The file contents as text, or an error message."
    )
    return _rclone_cat
