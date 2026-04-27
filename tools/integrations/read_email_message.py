"""Agent tool: read the body of a single email message."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def read_email_message(integration_id: str, folder: str, uid: str) -> str:
    """Fetch and format one message's envelope + plain-text body.

    Args:
        integration_id: Identifier of the email integration.
        folder: Mailbox the message lives in.
        uid: IMAP UID as returned by ``list_email_messages`` /
            ``search_email`` (the value in ``[brackets]`` in their output).

    Returns:
        Plain text — a header block followed by the body, or a short error
        notice if the UID isn't found.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "fetch_message",
            {"folder": folder, "uid": uid},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("read_email_message(%r, %r, %r) failed: %s", integration_id, folder, uid, exc)
        return f"Failed to read message {uid} in {folder!r}: {exc}"

    message = result.get("message", {})
    header = message.get("header", {})
    body = message.get("body_text", "").strip()
    attachments = message.get("attachments", []) or []
    head_block = (
        f"From: {header.get('from_', '')}\n"
        f"To: {header.get('to', '')}\n"
        f"Date: {header.get('date', '')}\n"
        f"Subject: {header.get('subject', '')}\n"
    )
    if attachments:
        head_block += "Attachments:\n"
        for att in attachments:
            head_block += (
                f"  - id={att.get('id', '')}  {att.get('filename', '(unnamed)')}"
                f"  ({att.get('mime_type', 'application/octet-stream')},"
                f" {_format_size(att.get('size', 0))})\n"
            )
    if not body:
        return head_block + "\n(no text body)"
    return head_block + "\n" + body


def _format_size(size: int) -> str:
    """Compact human-readable byte count: ``1.2KB`` / ``245KB`` / ``3.4MB``."""
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def build_read_email_message_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _read_email_message(integration_id: str, folder: str, uid: str) -> str:
        return await read_email_message(integration_id, folder, uid)

    _read_email_message.__name__ = read_email_message.__name__
    _read_email_message.__doc__ = (
        "Read one message's envelope + plain-text body. If the message has "
        "attachments, the header block lists them with an id you pass to "
        "``download_email_attachment`` to pull the bytes onto disk. Valid "
        f"integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to read from.\n"
        "    folder: Mailbox the message lives in (same value used in list_email_messages).\n"
        "    uid: IMAP UID of the message — the value shown in [brackets] by list_email_messages or search_email.\n\n"
        "Returns:\n"
        "    Plain text — a header block (From/To/Date/Subject, plus an "
        "Attachments list when present) followed by the body.\n"
    )
    return _read_email_message
