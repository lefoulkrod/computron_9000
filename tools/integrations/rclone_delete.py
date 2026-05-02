"""Agent tool: delete a file or directory on a connected rclone remote."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def rclone_delete(integration_id: str, remote_path: str) -> str:
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id, "delete", {"remote_path": remote_path},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning("rclone_delete(%r, %r) failed: %s", integration_id, remote_path, exc)
        return f"Failed to delete from {integration_id!r}: {exc}"

    if result.get("deleted"):
        return f"Deleted {remote_path!r} from {integration_id!r}."
    return f"Delete operation completed for {remote_path!r} on {integration_id!r}."


def build_rclone_delete_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _rclone_delete(integration_id: str, remote_path: str) -> str:
        return await rclone_delete(integration_id, remote_path)

    _rclone_delete.__name__ = rclone_delete.__name__
    _rclone_delete.__doc__ = (
        "Delete a file or directory on a connected rclone remote. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which storage integration to use.\n"
        "    remote_path: Remote path to delete.\n\n"
        "Returns:\n"
        "    A plain-text confirmation or error message."
    )
    return _rclone_delete
