"""Agent tool: search one mailbox for messages matching a text query."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def search_email(
    integration_id: str,
    query: str,
    folder: str = "INBOX",
    limit: int = 20,
) -> str:
    """Search one mailbox for messages whose headers or body contain ``query``.

    IMAP search is single-folder — to cover more than one folder, call this
    tool once per folder. Default folder is ``"INBOX"``.

    Args:
        integration_id: Identifier of the email integration.
        query: Text to match (headers or body).
        folder: Mailbox to search (default ``"INBOX"``).
        limit: Maximum matches to return (1-200, default 20).

    Returns:
        Plain text — one matched envelope per line, formatted as
        ``"- [uid] date  sender  —  subject"`` — or a short empty/error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "search_messages",
            {"folder": folder, "query": query, "limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("search_email(%r, %r, %r) failed: %s", integration_id, folder, query, exc)
        return f"Failed to search {folder!r}: {exc}"

    headers = result.get("headers", [])
    if not headers:
        return f"No matches for {query!r} in {folder!r}."
    lines = [_format_envelope(h) for h in headers]
    return f"Matches for {query!r} in {folder!r} ({len(lines)}):\n" + "\n".join(lines)


def _format_envelope(h: dict[str, Any]) -> str:
    uid = h.get("uid", "?")
    date = h.get("date") or ""
    sender = h.get("from_") or "(no sender)"
    subject = h.get("subject") or "(no subject)"
    return f"- [{uid}] {date}  {sender}  —  {subject}"


def build_search_email_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _search_email(
        integration_id: str,
        query: str,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> str:
        return await search_email(integration_id, query, folder, limit)

    _search_email.__name__ = search_email.__name__
    _search_email.__doc__ = (
        "Search one mailbox for messages whose headers or body contain "
        "``query``. IMAP search is single-folder — to cover more than one "
        'folder, call this tool once per folder. Default folder is "INBOX". '
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to search.\n"
        "    query: Text to match (headers or body).\n"
        '    folder: Mailbox to search (default "INBOX").\n'
        "    limit: Maximum matches to return (1-200, default 20).\n\n"
        "Returns:\n"
        "    Plain text — one matched envelope per line, formatted as "
        '"- [uid] date  sender  —  subject" — or a short empty/error notice.\n'
    )
    return _search_email
