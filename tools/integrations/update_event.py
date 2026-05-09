"""Agent tool: update an existing Google Calendar event."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def update_event(
    integration_id: str,
    calendar_url: str,
    event_id: str,
    summary: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> str:
    """Update fields on an existing calendar event.

    Only the fields you provide are changed; omitted fields stay as-is.

    Args:
        integration_id: Identifier of the calendar integration.
        calendar_url: URL of the calendar (from ``list_calendars``).
        event_id: ID of the event to update (from ``list_events``).
        summary: New event title (leave empty to keep current).
        start: New start time — RFC 3339 datetime or date string.
        end: New end time — same format as start.
        description: New description (leave empty to keep current).
        location: New location (leave empty to keep current).
        attendees: New attendee list — replaces the existing list entirely.

    Returns:
        A confirmation with the updated event, or an error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    args: dict[str, Any] = {
        "calendar_id": calendar_url,
        "event_id": event_id,
    }
    if summary:
        args["summary"] = summary
    if start:
        args["start"] = start
    if end:
        args["end"] = end
    if description:
        args["description"] = description
    if location:
        args["location"] = location
    if attendees is not None:
        args["attendees"] = attendees

    if len(args) == 2:
        return "No fields to update — provide at least one of summary, start, end, description, location, or attendees."

    try:
        result = await broker_client.call(
            integration_id, "update_event", args, app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "update_event(%r, %r) failed: %s", integration_id, event_id, exc,
        )
        return f"Failed to update event via {integration_id!r}: {exc}"

    event = result.get("event", {})
    title = event.get("summary", event_id)
    return f"Updated event '{title}' (event ID: {event_id})."


def build_update_event_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _update_event(
        integration_id: str,
        calendar_url: str,
        event_id: str,
        summary: str = "",
        start: str = "",
        end: str = "",
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> str:
        return await update_event(
            integration_id, calendar_url, event_id,
            summary, start, end, description, location, attendees,
        )

    _update_event.__name__ = update_event.__name__
    _update_event.__doc__ = (
        "Update an existing event on a Google Calendar. Only supplied fields "
        "are changed. Use list_events to get event IDs. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the calendar belongs to.\n"
        "    calendar_url: URL of the calendar (from list_calendars).\n"
        "    event_id: ID of the event (from list_events).\n"
        "    summary: New title (empty = keep current).\n"
        "    start: New start time, RFC 3339 or date.\n"
        "    end: New end time, RFC 3339 or date.\n"
        "    description: New description.\n"
        "    location: New location.\n"
        "    attendees: New attendee email list (replaces existing).\n\n"
        "Returns:\n"
        "    Plain text — a confirmation, or an error notice.\n"
    )
    return _update_event
