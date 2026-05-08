"""Google Calendar operations via the Calendar API v3."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class CalendarClient:
    """Thin wrapper around the Calendar v3 API."""

    def __init__(self, creds: Credentials) -> None:
        self._service = build("calendar", "v3", credentials=creds)

    def list_calendars(self) -> list[dict[str, Any]]:
        """List all calendar entries visible to the user."""
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            resp = (
                self._service.calendarList()
                .list(pageToken=page_token)
                .execute()
            )
            results.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results

    def list_events(
        self,
        calendar_id: str = "primary",
        *,
        days_forward: int = 30,
        days_back: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List events in a date range, recurring events expanded."""
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days_back)).isoformat()
        time_max = (now + timedelta(days=days_forward)).isoformat()

        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 250)
            resp = (
                self._service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=page_size,
                    pageToken=page_token,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            results.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        start: str,
        end: str,
        *,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an event. start/end are RFC 3339 timestamps or date strings."""
        body: dict[str, Any] = {"summary": summary}
        body["start"] = _time_body(start)
        body["end"] = _time_body(end)
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        return (
            self._service.events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        *,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Patch an existing event. Only supplied fields are updated."""
        body: dict[str, Any] = {}
        if summary is not None:
            body["summary"] = summary
        if start is not None:
            body["start"] = _time_body(start)
        if end is not None:
            body["end"] = _time_body(end)
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if attendees is not None:
            body["attendees"] = [{"email": a} for a in attendees]
        return (
            self._service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete an event from a calendar."""
        self._service.events().delete(
            calendarId=calendar_id, eventId=event_id,
        ).execute()


def _time_body(value: str) -> dict[str, str]:
    """Build a Calendar API start/end block from a date or datetime string.

    Pure date strings (YYYY-MM-DD) use the ``date`` key; anything longer
    is treated as an RFC 3339 ``dateTime``.
    """
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return {"date": value}
    return {"dateTime": value}
