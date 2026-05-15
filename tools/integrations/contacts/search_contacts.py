"""Agent tool: search contacts by name, email, or phone."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.contacts._format import format_contact

logger = logging.getLogger(__name__)


async def search_contacts(
    integration_id: str,
    query: str,
    limit: int = 20,
) -> str:
    """Search contacts by name, email, or phone number.

    Args:
        integration_id: Identifier of the contacts integration.
        query: Text to search for.
        limit: Maximum results to return (1-30, default 20).

    Returns:
        Plain-text listing of matching contacts, or a short error/empty notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "search_contacts",
            {"query": query, "limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("search_contacts(%r, %r) failed: %s", integration_id, query, exc)
        return f"Failed to search contacts: {exc}"

    contacts = result.get("contacts", [])
    if not contacts:
        return f"No contacts matching {query!r}."
    lines = [format_contact(c) for c in contacts]
    return f"Contact search results for {query!r} ({len(lines)}):\n" + "\n".join(lines)


def build_search_contacts_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _search_contacts(
        integration_id: str,
        query: str,
        limit: int = 20,
    ) -> str:
        return await search_contacts(integration_id, query, limit)

    _search_contacts.__name__ = search_contacts.__name__
    _search_contacts.__doc__ = (
        "Search contacts by name, email, or phone number. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to search.\n"
        "    query: Text to search for (name, email, or phone).\n"
        "    limit: Maximum results to return (1-30, default 20).\n\n"
        "Returns:\n"
        "    Plain text — one contact per line, or a short empty/error notice.\n"
    )
    return _search_contacts
