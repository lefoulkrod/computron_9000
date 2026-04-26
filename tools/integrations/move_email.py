"""Agent tool: move one email by UID from one folder to another."""

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
    uid: str,
    dest_folder: str,
) -> str:
    """Move one message by ``uid`` from ``folder`` to ``dest_folder``.

    The destination must already exist on the server (use
    ``list_email_folders`` to find candidate names — e.g. ``"Trash"``,
    ``"Archive"``, ``"[Gmail]/All Mail"``).

    Args:
        integration_id: Identifier of the email integration.
        folder: Source mailbox the message currently lives in.
        uid: IMAP UID of the message (from one of the listing tools).
        dest_folder: Destination mailbox to move it into.

    Returns:
        Plain text — a confirmation line, or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(
            integration_id,
            "move_message",
            {"folder": folder, "uid": uid, "dest_folder": dest_folder},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "move_email(%r, %r, %r -> %r) failed: %s",
            integration_id, folder, uid, dest_folder, exc,
        )
        return f"Failed to move {uid!r} from {folder!r} to {dest_folder!r}: {exc}"
    return f"Moved {uid!r} from {folder!r} to {dest_folder!r}."


def build_move_email_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _move_email(
        integration_id: str,
        folder: str,
        uid: str,
        dest_folder: str,
    ) -> str:
        return await move_email(integration_id, folder, uid, dest_folder)

    _move_email.__name__ = move_email.__name__
    _move_email.__doc__ = (
        "Move one email by UID from one folder to another. The destination "
        "must already exist on the server — call list_email_folders first "
        "to discover names. Useful for triage workflows: archive, trash, "
        f"or sort into project folders. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to move the message on.\n"
        "    folder: Source mailbox the message currently lives in.\n"
        "    uid: IMAP UID of the message (from list_email_messages or search_email).\n"
        "    dest_folder: Destination mailbox to move it into.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation line, or a short error notice.\n"
    )
    return _move_email
