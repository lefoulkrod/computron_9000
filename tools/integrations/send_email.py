"""Agent tool: send an email through a connected integration's SMTP."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def send_email(
    integration_id: str,
    to: list[str],
    subject: str,
    body: str,
) -> str:
    """Send a plain-text email through ``integration_id``.

    Args:
        integration_id: Identifier of the email integration to send through.
        to: One or more recipient addresses.
        subject: Subject line.
        body: Plain-text message body.

    Returns:
        Plain text — a confirmation line including the assigned
        ``Message-ID``, or a short error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "send_message",
            {"to": list(to), "subject": subject, "body": body},
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


def build_send_email_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _send_email(
        integration_id: str,
        to: list[str],
        subject: str,
        body: str,
    ) -> str:
        return await send_email(integration_id, to, subject, body)

    _send_email.__name__ = send_email.__name__
    _send_email.__doc__ = (
        "Send a plain-text email through a connected integration. The "
        "From address is the integration's own account — the agent does "
        f"not choose it. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to send through.\n"
        "    to: One or more recipient addresses.\n"
        "    subject: Subject line.\n"
        "    body: Plain-text message body.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation line, or a short error notice.\n"
    )
    return _send_email
