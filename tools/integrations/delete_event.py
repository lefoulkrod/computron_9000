"""Agent tool: delete an event from a Google Calendar."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def delete_event(
    integration_id: str,
    calendar_url: str,
    event_id: str,
) -> str:
    """Delete an event from a calendar.

    Args:
        integration_id: Identifier of the calendar integration.
        calendar_url: URL of the calendar (from ``list_calendars``).
        event_id: ID of the event to delete (from ``list_events``).

    Returns:
        A confirmation, or an error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(
            integration_id,
            "delete_event",
            {"calendar_id": calendar_url, "event_id": event_id},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "delete_event(%r, %r) failed: %s", integration_id, event_id, exc,
        )
        return f"Failed to delete event via {integration_id!r}: {exc}"

    return f"Deleted event {event_id} from calendar."


def build_delete_event_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _delete_event(
        integration_id: str,
        calendar_url: str,
        event_id: str,
    ) -> str:
        return await delete_event(integration_id, calendar_url, event_id)

    _delete_event.__name__ = delete_event.__name__
    _delete_event.__doc__ = (
        "Delete an event from a Google Calendar. This is permanent — the "
        "event cannot be recovered. Use list_events to get event IDs. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the calendar belongs to.\n"
        "    calendar_url: URL of the calendar (from list_calendars).\n"
        "    event_id: ID of the event to delete (from list_events).\n\n"
        "Returns:\n"
        "    Plain text — a confirmation, or an error notice.\n"
    )
    return _delete_event
