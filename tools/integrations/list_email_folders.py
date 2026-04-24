"""Agent tool: list the folders (mailboxes) of a connected email integration."""

from __future__ import annotations

import logging

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def list_email_folders(integration_id: str) -> str:
    """List the folders (mailboxes) available on a connected email integration.

    Args:
        integration_id: Identifier of the email integration to query (e.g.
            ``"icloud_personal"``). The agent sees valid ids in the dynamic
            description of this tool.

    Returns:
        A plain-text message — either a bulleted folder list, a
        "not connected" notice, or an error description suitable to surface
        verbatim.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_mailboxes",
            {},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_email_folders(%r) failed: %s", integration_id, exc)
        return f"Failed to list folders for {integration_id!r}: {exc}"

    folders = [m["name"] for m in result.get("mailboxes", [])]
    if not folders:
        return f"No folders found on {integration_id!r}."
    joined = "\n".join(f"- {name}" for name in folders)
    return f"Folders on {integration_id!r}:\n{joined}"
