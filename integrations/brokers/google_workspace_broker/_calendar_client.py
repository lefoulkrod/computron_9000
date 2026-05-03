"""Google Calendar read operations via the Calendar API v3."""

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
