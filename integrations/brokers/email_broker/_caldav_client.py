"""CalDAV client for the email broker.

Thin async wrapper around the synchronous :mod:`caldav` library. Mirrors
the IMAP client's contract:

- Every blocking ``caldav`` call runs through ``asyncio.to_thread`` so
  the event loop stays responsive while a HTTP-PROPFIND or REPORT is in
  flight.
- An ``asyncio.Lock`` serializes access to the underlying ``DAVClient``.
  caldav's library is documented as not fully thread-safe, and serial
  access matches what we already do for IMAP.

The credential is held in memory for the broker's lifetime — same pattern
as the IMAP client. The broker's ``__main__`` wipes it from
``os.environ`` after handing it here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import caldav
import requests.exceptions
import urllib3.exceptions

from integrations.brokers.email_broker.types import Calendar, Event

logger = logging.getLogger(__name__)

# Errors that indicate the underlying HTTP connection has gone away —
# server-side idle close, RST, half-closed TLS. caldav uses requests under
# the hood, so the visible shapes are requests/urllib3 errors. Auth failures
# stay in their own ``AuthorizationError`` branch — retrying those would
# loop on a real credential rejection.
_STALE_CONN_ERRORS: tuple[type[BaseException], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    urllib3.exceptions.ProtocolError,
)


class CalDavAuthError(Exception):
    """Server rejected the credential. The broker's entry code maps this to exit(77)."""


class CalDavClient:
    """Single CalDAV session shared by all concurrent verb calls in this broker."""

    def __init__(self, *, url: str, username: str, password: str) -> None:
        self._url = url
        self._username = username
        # Held on the instance so the broker can refresh credentials on
        # transient errors without keeping the secret in env.
        self._password = password

        self._lock = asyncio.Lock()
        self._client: caldav.DAVClient | None = None
        self._principal: Any | None = None

    async def connect(self) -> None:
        """Open the CalDAV session and resolve the user's principal.

        Auth failures (HTTP 401) raise :class:`CalDavAuthError` so the
        broker's entry code can exit 77 — same shape as IMAP's auth flow.
        """
        try:
            self._client, self._principal = await asyncio.to_thread(self._blocking_connect)
        except caldav.lib.error.AuthorizationError as exc:
            msg = f"CalDAV auth rejected: {exc}"
            raise CalDavAuthError(msg) from exc
        except Exception as exc:
            # The library wraps most errors in caldav.lib.error.* — any one
            # whose status is 401 we treat as auth rejection so the broker
            # exits 77 and the supervisor flips state to ``auth_failed``.
            if _is_auth_failure(exc):
                msg = f"CalDAV auth rejected: {exc}"
                raise CalDavAuthError(msg) from exc
            raise
        logger.info("CalDAV principal resolved (%s @ %s)", self._username, self._url)

    def _blocking_connect(self) -> tuple[caldav.DAVClient, Any]:
        """Synchronous connect — runs inside a worker thread.

        Used by ``connect()`` and as the reconnect path inside
        ``_with_reconnect``.
        """
        client = caldav.DAVClient(
            url=self._url,
            username=self._username,
            password=self._password,
        )
        # Resolving the principal exercises the auth path; if creds are
        # rejected this is where it surfaces.
        principal = client.principal()
        return client, principal

    def _with_reconnect(self, op):
        """Run ``op(client, principal)``; reconnect+retry once on stale-conn errors.

        Caller must hold ``self._lock`` and must have awaited ``connect()``
        first. iCloud closes idle DAV sessions after ~10–30 minutes; the
        next request fails with a requests/urllib3 connection error. We
        rebuild the DAVClient + principal and retry once. A second failure
        propagates.

        Auth errors are *not* caught here — they're bubbled up so the
        broker's entry code can map them to exit 77.
        """
        if self._client is None or self._principal is None:
            msg = "CalDavClient used before connect()"
            raise RuntimeError(msg)
        try:
            return op(self._client, self._principal)
        except _STALE_CONN_ERRORS as exc:
            logger.info("CalDAV connection stale (%s); reconnecting and retrying once", exc)
            client, principal = self._blocking_connect()
            self._client = client
            self._principal = principal
            return op(client, principal)

    async def list_calendars(self) -> list[Calendar]:
        """Return the user's calendars (collections under their principal)."""
        async with self._lock:

            def _op(_client: caldav.DAVClient, principal: Any) -> list[Any]:
                return list(principal.calendars())

            cals = await asyncio.to_thread(self._with_reconnect, _op)

        return [
            Calendar(
                name=_calendar_name(c),
                url=str(c.url),
            )
            for c in cals
        ]

    async def list_events(
        self,
        calendar_url: str,
        days_forward: int,
        days_back: int,
        limit: int,
    ) -> tuple[str, list[Event]]:
        """List events on ``calendar_url`` over a centered date range.

        Returns ``(calendar_name, events)``. The name is fetched alongside
        the search so the caller can present human-readable output without
        a second round-trip; recurring events are server-expanded into
        per-occurrence records.
        """
        limit = max(1, min(limit, 200))
        async with self._lock:

            def _op(client: caldav.DAVClient, _principal: Any) -> tuple[str, list[Any]]:
                cal = client.calendar(url=calendar_url)
                name = _calendar_name(cal)
                now = datetime.now(UTC)
                start = now - timedelta(days=days_back)
                end = now + timedelta(days=days_forward)
                # ``event=True`` filters out tasks/journals; ``expand=True``
                # asks the server to materialize each recurrence into its
                # own VEVENT so the parser doesn't need to walk RRULEs.
                hits = list(cal.search(
                    start=start, end=end, event=True, expand=True,
                ))
                return name, hits

            name, raw = await asyncio.to_thread(self._with_reconnect, _op)

        logger.info(
            "list_events(%s, +%d/-%d days): %d raw hits",
            calendar_url, days_forward, days_back, len(raw),
        )
        events: list[Event] = []
        skipped = 0
        for hit in raw:
            ev = _parse_event(hit)
            if ev is None:
                skipped += 1
                continue
            events.append(ev)
            if len(events) >= limit:
                break
        if skipped:
            logger.info("list_events: skipped %d unparseable hit(s)", skipped)
        return name, events


# ── helpers ──────────────────────────────────────────────────────────────────


def _is_auth_failure(exc: Exception) -> bool:
    """True if ``exc`` is the caldav lib's flavor of HTTP 401."""
    # caldav wraps HTTP errors in error.DAVError subclasses with a
    # ``.reason`` attribute; the 401 case maps to AuthorizationError but
    # other paths can come through as bare HTTP errors. Sniff for the
    # 401 status text rather than coupling to one library version's
    # exception hierarchy.
    text = str(exc).lower()
    return "401" in text or "unauthorized" in text


def _calendar_name(cal: Any) -> str:
    """Extract the human-readable display name from a CalDAV calendar object.

    caldav exposes ``Calendar.name`` as a lazy property that fetches the
    displayname from the server; the fetch can raise from any layer of
    the HTTP/DAV/network stack. Treat any failure as "no name available"
    and fall back to the URL's last segment — always-safe identifier.
    """
    name: Any | None = None
    with contextlib.suppress(Exception):
        name = cal.name
    if name:
        return str(name)
    url = str(cal.url).rstrip("/")
    return url.rsplit("/", 1)[-1] or url


def _parse_event(hit: Any) -> Event | None:
    """Convert a caldav search hit into our :class:`Event` shape.

    Returns ``None`` if the hit doesn't carry a usable VEVENT (e.g. the
    server returned a freebusy block). Robust to missing fields — every
    field but ``uid`` is optional in our type, and the iCalendar payload
    routinely omits ``DESCRIPTION`` / ``LOCATION`` / ``DTEND``.

    caldav 3.x exposes the parsed iCalendar tree at
    ``hit.icalendar_instance`` — an :class:`icalendar.Calendar` whose
    ``walk("VEVENT")`` yields the event component(s).
    """
    ical = getattr(hit, "icalendar_instance", None)
    if ical is None:
        return None
    vevent = next(iter(ical.walk("VEVENT")), None)
    if vevent is None:
        return None

    uid = _ical_str(vevent, "uid")
    if not uid:
        return None
    return Event(
        uid=uid,
        summary=_ical_str(vevent, "summary"),
        start=_ical_dt(vevent, "dtstart"),
        end=_ical_dt(vevent, "dtend"),
        location=_ical_str(vevent, "location"),
        description=_ical_str(vevent, "description"),
    )


def _ical_str(vevent: Any, field: str) -> str:
    """Read a VEVENT property as a plain unicode string."""
    value = vevent.get(field)
    if value is None:
        return ""
    return str(value)


def _ical_dt(vevent: Any, field: str) -> str:
    """Read a VEVENT date/datetime property as ISO 8601.

    All-day events use ``VALUE=DATE`` (a python ``date``); regular events
    use a tz-aware ``datetime``. Both have ``isoformat()``.
    """
    value = vevent.get(field)
    if value is None:
        return ""
    dt = getattr(value, "dt", None)
    if dt is None:
        return str(value)
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)
