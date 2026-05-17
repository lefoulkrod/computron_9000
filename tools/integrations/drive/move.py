"""Agent tool: move or rename an entry in a Drive integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def drive_move(
    integration_id: str,
    handle: str,
    dest_parent_handle: str = "",
    name: str = "",
) -> str:
    """Move an entry into a different folder and/or rename it.

    Args:
        integration_id: Which Drive integration to use.
        handle: Handle of the entry to move.
        dest_parent_handle: Destination folder handle (empty = root). Pass the
            entry's current parent here if you only want to rename in place.
        name: Optional new name for the entry. Empty keeps the current name.

    Returns:
        Plain text — move confirmation with the resulting handle.
    """
    if not name and not dest_parent_handle:
        return "drive_move needs either a new name or a destination folder handle."
    app_sock = load_config().integrations.app_sock_path
    args: dict[str, Any] = {"handle": handle, "dest_parent_handle": dest_parent_handle}
    if name:
        args["name"] = name
    try:
        result = await broker_client.call(
            integration_id, "drive_move", args, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_move(%r, %r -> %r) failed: %s", integration_id, handle, dest_parent_handle, exc)
        return f"Failed to move {handle!r}: {exc}"

    entry = result.get("entry", {})
    new_handle = entry.get("handle", "?")
    new_name = entry.get("name", name or "?")
    return f"Moved to {new_name!r}. Handle: {new_handle}"


def build_drive_move_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_move(
        integration_id: str, handle: str, dest_parent_handle: str = "", name: str = "",
    ) -> str:
        return await drive_move(integration_id, handle, dest_parent_handle, name)

    _drive_move.__name__ = drive_move.__name__
    _drive_move.__doc__ = (
        "Move an entry into a different folder and/or rename it. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Drive integration to use.\n"
        "    handle: Handle of the entry to move.\n"
        "    dest_parent_handle: Destination folder handle (empty = root).\n"
        "    name: Optional new name (empty keeps the current name).\n\n"
        "Returns:\n"
        "    Plain text — move confirmation with the resulting handle.\n"
    )
    return _drive_move
