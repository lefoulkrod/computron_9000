"""Agent tool: list calendars on a connected calendar integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def list_calendars(integration_id: str) -> str:
    """List the calendars (collections) available on a connected integration.

    Args:
        integration_id: Identifier of the calendar integration to query.

    Returns:
        A plain-text bulleted list of calendar names with the URL the agent
        passes back into ``list_events``, or a short empty/error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_calendars",
            {},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_calendars(%r) failed: %s", integration_id, exc)
        return f"Failed to list calendars for {integration_id!r}: {exc}"

    calendars = result.get("calendars", [])
    if not calendars:
        return f"No calendars found on {integration_id!r}."
    lines = [f"- {c.get('name') or '(unnamed)'}  —  {c.get('url', '')}" for c in calendars]
    return f"Calendars on {integration_id!r}:\n" + "\n".join(lines)


def build_list_calendars_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_calendars(integration_id: str) -> str:
        return await list_calendars(integration_id)

    _list_calendars.__name__ = list_calendars.__name__
    _list_calendars.__doc__ = (
        "List the calendars on a connected calendar integration. Each line "
        "carries the calendar's URL, which is the value to pass to "
        f"``list_events``. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to list calendars on.\n\n"
        "Returns:\n"
        "    Plain text — one calendar per line as "
        '"- name  —  <url>", or a short empty/error notice.\n'
    )
    return _list_calendars
