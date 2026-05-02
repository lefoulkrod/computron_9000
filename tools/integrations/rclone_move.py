"""Agent tool: move files between local and rclone remote storage."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_move(
    integration_id: str,
    source: str,
    destination: str,
) -> str:
    """Move a file between local and remote storage.

    Direction is determined by path prefixes:
    - If source starts with "remote:" or "remote/", it's a remote-to-local move.
    - Otherwise, it's a local-to-remote move.
    """
    app_sock = load_config().integrations.app_sock_path

    # Determine direction from source path
    is_from_remote = source.startswith("remote:") or source.startswith("remote/")

    if is_from_remote:
        # remote -> local
        remote_path = source.removeprefix("remote:").removeprefix("/")
        local_path = destination
        args = {"remote_path": remote_path}
        if local_path:
            args["local_path"] = local_path
        verb = "move_from_remote"
    else:
        # local -> remote
        local_path = source
        remote_path = destination.removeprefix("remote:").removeprefix("/")
        args = {"local_path": local_path, "remote_path": remote_path}
        verb = "move_to_remote"

    try:
        result = await broker_client.call(
            integration_id, verb, args,
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_move(%r, %r, %r) failed: %s", integration_id, source, destination, exc)
        return f"Failed to move for {integration_id!r}: {exc}"

    if is_from_remote:
        local_path = result.get("local_path", "")
        bytes_moved = result.get("bytes_moved", 0)
        return f"Moved {bytes_moved:,} bytes from {integration_id!r} to {local_path!r}."
    else:
        bytes_moved = result.get("bytes_moved", 0)
        remote_path = result.get("remote_path", "")
        return f"Moved {bytes_moved:,} bytes to {integration_id!r} at {remote_path!r}."


def build_rclone_move_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_move(integration_id: str, source: str, destination: str) -> str:
        return await rclone_move(integration_id, source, destination)

    _rclone_move.__name__ = rclone_move.__name__
    _rclone_move.__doc__ = (
        "Move a file between local and remote storage. Direction is determined "
        "by the source path: if it starts with 'remote:' or 'remote/', the move "
        f"goes from remote to local; otherwise local to remote. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to use.\n"
        "    source: Source path (local file path or 'remote:/path').\n"
        "    destination: Destination path (local file path or 'remote:/path').\n\n"
        "Returns:\n"
        "    A plain-text confirmation or error message."
    )
    return _rclone_move
