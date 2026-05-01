"""Agent tool: download one attachment from a message to local disk."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def download_email_attachment(
    integration_id: str,
    folder: str,
    uid: str,
    attachment_id: str,
) -> str:
    """Download one attachment to the local virtual-computer uploads folder.

    Args:
        integration_id: Identifier of the email integration.
        folder: Mailbox the message lives in.
        uid: IMAP UID of the message.
        attachment_id: Attachment id from ``read_email_message``'s
            ``Attachments`` list — the ``id=...`` value on that line.

    Returns:
        Plain text — the on-disk path the agent can pass to other tools
        (``describe_image``, ``read_file``, etc.), or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "fetch_attachment",
            {"folder": folder, "uid": uid, "attachment_id": attachment_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "download_email_attachment(%r, %r, %r, %r) failed: %s",
            integration_id, folder, uid, attachment_id, exc,
        )
        return (
            f"Failed to download attachment {attachment_id!r} "
            f"from {uid!r}: {exc}"
        )

    path = result.get("path", "")
    filename = result.get("filename") or "(unnamed)"
    size = result.get("size", 0)
    return f"Saved {filename!r} to {path} ({_format_size(size)})."


def _format_size(size: int) -> str:
    """Compact human-readable byte count — same shape as the listing tool."""
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def build_download_email_attachment_tool(
    integration_ids: Iterable[str],
) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _download_email_attachment(
        integration_id: str,
        folder: str,
        uid: str,
        attachment_id: str,
    ) -> str:
        return await download_email_attachment(
            integration_id, folder, uid, attachment_id,
        )

    _download_email_attachment.__name__ = download_email_attachment.__name__
    _download_email_attachment.__doc__ = (
        "Download one attachment from a message onto the local filesystem. "
        "Returns the on-disk path, which can be passed to any tool that "
        f"takes a file path. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the message lives on.\n"
        "    folder: Mailbox the message is in.\n"
        "    uid: IMAP UID of the message.\n"
        "    attachment_id: Id from the message's Attachments line.\n\n"
        "Returns:\n"
        "    Plain text — the saved path with original filename and size, "
        "or a short error notice.\n"
    )
    return _download_email_attachment
