"""Agent tool: list contacts on a connected Google Workspace integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.contacts._format import format_contact

logger = logging.getLogger(__name__)


async def list_contacts(integration_id: str, limit: int = 50) -> str:
    """List contacts on a connected integration.

    Args:
        integration_id: Identifier of the contacts integration.
        limit: Maximum contacts to return (1-200, default 50).

    Returns:
        Plain-text listing of contacts, or a short error/empty notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_contacts",
            {"limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_contacts(%r) failed: %s", integration_id, exc)
        return f"Failed to list contacts: {exc}"

    contacts = result.get("contacts", [])
    if not contacts:
        return "No contacts found."
    lines = [format_contact(c) for c in contacts]
    return f"Contacts ({len(lines)}):\n" + "\n".join(lines)


def build_list_contacts_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_contacts(integration_id: str, limit: int = 50) -> str:
        return await list_contacts(integration_id, limit)

    _list_contacts.__name__ = list_contacts.__name__
    _list_contacts.__doc__ = (
        "List contacts on a connected integration. Returns one contact per "
        "line with name, email, and phone when available. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to list contacts from.\n"
        "    limit: Maximum contacts to return (1-200, default 50).\n\n"
        "Returns:\n"
        "    Plain text — one contact per line, or a short empty/error notice.\n"
    )
    return _list_contacts
