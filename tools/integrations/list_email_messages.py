"""Agent tool: list recent messages in an email folder."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def list_email_messages(integration_id: str, folder: str, limit: int = 20) -> str:
    """List the most recent messages in ``folder`` for ``integration_id``.

    Args:
        integration_id: Identifier of the email integration.
        folder: Mailbox name (e.g. ``"INBOX"``). Use ``list_email_folders``
            to discover valid names.
        limit: Maximum number of messages to return (1–200, default 20).

    Returns:
        A plain-text bulleted list of envelopes, or a short error/empty
        notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_messages",
            {"folder": folder, "limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_email_messages(%r, %r) failed: %s", integration_id, folder, exc)
        return f"Failed to list messages in {folder!r}: {exc}"

    headers = result.get("headers", [])
    if not headers:
        return f"No messages in {folder!r}."
    lines = [_format_envelope(h) for h in headers]
    return f"Recent messages in {folder!r} ({len(lines)}):\n" + "\n".join(lines)


def _format_envelope(h: dict[str, Any]) -> str:
    uid = h.get("uid", "?")
    date = h.get("date") or ""
    sender = h.get("from_") or "(no sender)"
    subject = h.get("subject") or "(no subject)"
    return f"- [{uid}] {date}  {sender}  —  {subject}"


def build_list_email_messages_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_email_messages(integration_id: str, folder: str, limit: int = 20) -> str:
        return await list_email_messages(integration_id, folder, limit)

    _list_email_messages.__name__ = list_email_messages.__name__
    _list_email_messages.__doc__ = (
        "List the most recent messages in a mailbox. Returns an envelope per "
        f"line with the UID in brackets. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to read from.\n"
        "    folder: Mailbox name. Call list_email_folders first if unsure.\n"
        "    limit: Maximum messages to return (1-200, default 20).\n\n"
        "Returns:\n"
        "    Plain text — one envelope per line, formatted as "
        '"- [uid] date  sender  —  subject".\n'
    )
    return _list_email_messages
