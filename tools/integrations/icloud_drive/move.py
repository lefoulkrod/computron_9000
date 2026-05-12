"""Agent tool: move a file to/from a connected iCloud Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.icloud_drive._format import human_bytes, split_remote_arg

logger = logging.getLogger(__name__)


async def icloud_drive_move(integration_id: str, source: str, destination: str) -> str:
    """Move a file between the local filesystem and an iCloud Drive integration.

    Prefix a path with ``remote:`` to mean a path on the Drive; a bare path is
    a local filesystem path. Exactly one of ``source`` / ``destination`` must
    be remote.

    Args:
        integration_id: Which iCloud Drive integration to use.
        source: Source path — ``remote:Docs/a.txt`` or a local path.
        destination: Destination path — ``remote:Docs/b.txt`` or a local path.

    Returns:
        A plain-text confirmation, or an error / permission notice.
    """
    src_remote, src_path = split_remote_arg(source)
    dst_remote, dst_path = split_remote_arg(destination)
    if src_remote == dst_remote:
        return "Exactly one of source/destination must be a remote path (prefixed with 'remote:')."

    if src_remote:
        verb = "move_from_remote"
        args: dict[str, Any] = {"remote_path": src_path}
        if dst_path:
            args["local_path"] = dst_path
    else:
        verb = "move_to_remote"
        args = {"local_path": src_path, "remote_path": dst_path}

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(integration_id, verb, args, app_sock_path=app_sock)
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("icloud_drive_move(%r, %r -> %r) failed: %s", integration_id, source, destination, exc)
        return f"Failed to move {source!r} -> {destination!r}: {exc}"

    n = int(result.get("bytes_moved", 0) or 0)
    if src_remote:
        return f"Moved {src_path!r} ({human_bytes(n)}) to {result.get('local_path', dst_path)}."
    return f"Moved {src_path!r} ({human_bytes(n)}) to {result.get('remote_path', dst_path)!r} on the remote."


def build_icloud_drive_move_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _icloud_drive_move(integration_id: str, source: str, destination: str) -> str:
        return await icloud_drive_move(integration_id, source, destination)

    _icloud_drive_move.__name__ = icloud_drive_move.__name__
    _icloud_drive_move.__doc__ = (
        "Move a file between the local filesystem and an iCloud Drive "
        "integration. Prefix a path with 'remote:' for a Drive path; a bare "
        "path is local. Exactly one side must be remote. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which iCloud Drive integration to use.\n"
        "    source: Source path — 'remote:Docs/a.txt' or a local path.\n"
        "    destination: Destination path — 'remote:Docs/b.txt' or a local path.\n\n"
        "Returns:\n"
        "    Plain text — move confirmation.\n"
    )
    return _icloud_drive_move
