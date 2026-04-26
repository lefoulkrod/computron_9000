"""Agent tool: list events on a calendar over a centered date range."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def list_events(
    integration_id: str,
    calendar_url: str,
    days_forward: int = 30,
    days_back: int = 0,
    limit: int = 50,
) -> str:
    """List events on a calendar over a date range centered on today.

    Recurring events are expanded into per-occurrence rows, so a weekly
    meeting in a 30-day window appears as ~4 separate lines.

    Args:
        integration_id: Identifier of the calendar integration.
        calendar_url: URL of the calendar (from ``list_calendars``).
        days_forward: How many days into the future to include (1-365,
            default 30).
        days_back: How many days into the past to include (0-365, default 0
            — only future events).
        limit: Maximum events to return (1-200, default 50).

    Returns:
        A plain-text bulleted list of events, or a short empty/error notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_events",
            {
                "calendar_url": calendar_url,
                "days_forward": days_forward,
                "days_back": days_back,
                "limit": limit,
            },
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "list_events(%r, %r) failed: %s", integration_id, calendar_url, exc,
        )
        return f"Failed to list events for {integration_id!r}: {exc}"

    events = result.get("events", [])
    # Prefer the human-readable calendar name; fall back to the URL if the
    # broker didn't supply one (older broker / unparsed response).
    label = result.get("calendar_name") or calendar_url
    if not events:
        return f"No events on {label!r} in this range."
    lines = [_format_event(e) for e in events]
    return f"Events on {label!r} ({len(lines)}):\n" + "\n".join(lines)


def _format_event(e: dict[str, Any]) -> str:
    start = e.get("start") or "(no start)"
    summary = e.get("summary") or "(no title)"
    location = e.get("location") or ""
    suffix = f"  @ {location}" if location else ""
    return f"- {start}  {summary}{suffix}"


def build_list_events_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_events(
        integration_id: str,
        calendar_url: str,
        days_forward: int = 30,
        days_back: int = 0,
        limit: int = 50,
    ) -> str:
        return await list_events(
            integration_id, calendar_url, days_forward, days_back, limit,
        )

    _list_events.__name__ = list_events.__name__
    _list_events.__doc__ = (
        "List events on a calendar over a date range centered on today. "
        "Recurring events are expanded — a weekly meeting in a 30-day "
        "window appears as ~4 lines. The output header carries the "
        "calendar's display name; the agent passes the URL in to scope "
        f"the query. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration the calendar belongs to.\n"
        "    calendar_url: URL of the calendar — call list_calendars first to discover.\n"
        "    days_forward: Days into the future to include (1-365, default 30).\n"
        "    days_back: Days into the past to include (0-365, default 0).\n"
        "    limit: Maximum events to return (1-200, default 50).\n\n"
        "Returns:\n"
        "    Plain text — one event per line as "
        '"- start  summary [@ location]", or a short empty/error notice.\n'
    )
    return _list_events
