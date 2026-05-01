"""Agent tool: send an email through a connected integration's SMTP."""

from __future__ import annotations

import base64
import logging
import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def send_email(
    integration_id: str,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[str] | None = None,
) -> str:
    """Send an email through ``integration_id``, optionally with attachments.

    Args:
        integration_id: Identifier of the email integration to send through.
        to: One or more recipient addresses.
        subject: Subject line.
        body: Plain-text message body.
        attachments: Optional list of file paths. Each file is read, the
            content type is guessed from the extension (falling back to
            ``application/octet-stream``), and the file is attached under
            its basename.

    Returns:
        Plain text — a confirmation line including the assigned
        ``Message-ID``, or a short error notice.
    """
    args: dict[str, Any] = {"to": list(to), "subject": subject, "body": body}
    if attachments:
        encoded, error = _encode_attachments(attachments)
        if error is not None:
            return error
        args["attachments"] = encoded

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "send_message",
            args,
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "send_email(%r, to=%r) failed: %s", integration_id, to, exc,
        )
        return f"Failed to send via {integration_id!r}: {exc}"

    message_id = result.get("message_id", "")
    audience = ", ".join(to)
    if message_id:
        return f"Sent via {integration_id!r} to {audience} (Message-ID: {message_id})."
    return f"Sent via {integration_id!r} to {audience}."


def _encode_attachments(
    paths: list[str],
) -> tuple[list[dict[str, str]], str | None]:
    """Read each path; return the wire-shaped list or a user-facing error string.

    Errors return ``(_, message)`` rather than raising so the agent gets a
    plain-text explanation instead of a stack trace; this matches every
    other early-exit shape in the integrations tools.
    """
    out: list[dict[str, str]] = []
    for path_str in paths:
        path = Path(path_str)
        try:
            data = path.read_bytes()
        except OSError as exc:
            return [], f"Cannot read attachment {path_str!r}: {exc}"
        mime_type = mimetypes.guess_type(path_str)[0] or "application/octet-stream"
        out.append({
            "filename": path.name,
            "mime_type": mime_type,
            "data_b64": base64.b64encode(data).decode("ascii"),
        })
    return out, None


def build_send_email_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _send_email(
        integration_id: str,
        to: list[str],
        subject: str,
        body: str,
        attachments: list[str] | None = None,
    ) -> str:
        return await send_email(integration_id, to, subject, body, attachments)

    _send_email.__name__ = send_email.__name__
    _send_email.__doc__ = (
        "Send an email through a connected integration, optionally with "
        "file attachments. The From address is the integration's own "
        "account — the agent does not choose it. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to send through.\n"
        "    to: One or more recipient addresses.\n"
        "    subject: Subject line.\n"
        "    body: Plain-text message body.\n"
        "    attachments: Optional list of file paths to attach.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation line, or a short error notice.\n"
    )
    return _send_email
