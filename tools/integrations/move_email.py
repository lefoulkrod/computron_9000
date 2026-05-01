"""Agent tool: move one or more emails by UID from one folder to another."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def move_email(
    integration_id: str,
    folder: str,
    uids: list[str],
    dest_folder: str,
) -> str:
    """Move one or more messages from ``folder`` to ``dest_folder``.

    The destination must already exist — use ``list_email_folders`` to
    find candidate names (e.g. ``"Trash"``, ``"Archive"``).

    Args:
        integration_id: Identifier of the email integration.
        folder: Source mailbox.
        uids: List of message UIDs from a listing tool. Up to 200 per call.
        dest_folder: Destination mailbox.

    Returns:
        Plain text — a confirmation line, or a short error notice.
    """
    if not uids:
        return "No UIDs supplied — nothing to move."
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(
            integration_id,
            "move_messages",
            {"folder": folder, "uids": list(uids), "dest_folder": dest_folder},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "move_email(%r, %r, %d uid(s) -> %r) failed: %s",
            integration_id, folder, len(uids), dest_folder, exc,
        )
        return (
            f"Failed to move {len(uids)} message(s) from {folder!r} "
            f"to {dest_folder!r}: {exc}"
        )
    noun = "message" if len(uids) == 1 else "messages"
    return f"Moved {noun} from {folder!r} to {dest_folder!r}."


def build_move_email_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _move_email(
        integration_id: str,
        folder: str,
        uids: list[str],
        dest_folder: str,
    ) -> str:
        return await move_email(integration_id, folder, uids, dest_folder)

    _move_email.__name__ = move_email.__name__
    _move_email.__doc__ = (
        "Move one or more emails from one folder to another. The "
        "destination must already exist — call list_email_folders to "
        "discover names. Useful for triage: archive, trash, or sort "
        f"into project folders. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to move messages on.\n"
        "    folder: Source mailbox.\n"
        "    uids: List of message UIDs from a listing tool. Up to 200 per call.\n"
        "    dest_folder: Destination mailbox.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation line, or a short error notice.\n"
    )
    return _move_email
