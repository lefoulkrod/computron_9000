"""Pydantic models for the email broker's domain types.

These represent the email-domain data (mailboxes, messages, headers) the
broker's clients exchange internally and that the dispatcher serializes into
JSON frames at the wire boundary.

Imports only stdlib and pydantic — no internal dependencies — so this module
can be imported from anywhere in the email broker (clients, verbs, dispatcher,
tests) without introducing a cycle.
"""

from __future__ import annotations

from pydantic import BaseModel


class Mailbox(BaseModel):
    r"""One IMAP mailbox (folder).

    Attributes:
        name: Fully qualified mailbox name (e.g. ``"INBOX"``, ``"Sent Messages"``).
        attrs: Mailbox flags from IMAP ``LIST`` output — IMAP's standard
            ``\HasChildren`` / ``\HasNoChildren`` / ``\Noselect`` plus
            special-use flags like ``\Sent``, ``\Trash``, ``\Drafts``
            (RFC 6154). Kept as-is so callers can filter on them without the
            broker having to anticipate every flag vendors might emit.
    """

    name: str
    attrs: list[str]


class MessageHeader(BaseModel):
    """Lightweight message envelope — enough to show a list/search hit.

    ``uid`` is the IMAP UID (stable across the session's lifetime of the
    mailbox), not the sequence number. Callers round-trip the ``(folder, uid)``
    pair back to :meth:`ImapClient.fetch_message` to read the body.
    """

    uid: str
    folder: str
    from_: str = ""
    to: str = ""
    subject: str = ""
    date: str = ""


class Message(BaseModel):
    """Full message body + envelope.

    ``body_text`` is the best-effort plain-text rendering (MIME multipart
    falls back to the ``text/plain`` part, or to a stripped ``text/html``
    part when no plain alternative exists).
    """

    header: MessageHeader
    body_text: str = ""


class Calendar(BaseModel):
    """One CalDAV calendar (collection)."""

    name: str
    """Display name of the calendar (e.g. ``"Home"``, ``"Work"``)."""

    url: str
    """Server URL for the collection — opaque identifier the agent passes
    back into ``list_events`` to scope a query."""


class Event(BaseModel):
    """One occurrence of a calendar event.

    Recurring events are *expanded* into per-occurrence ``Event`` records
    over the queried date range, so the caller doesn't need to interpret
    RRULEs themselves.
    """

    uid: str
    """iCalendar UID — globally stable identifier for this event series."""

    summary: str = ""
    """Event title."""

    start: str = ""
    """ISO-8601 start datetime, or ``YYYY-MM-DD`` for all-day events."""

    end: str = ""
    """ISO-8601 end datetime, or ``YYYY-MM-DD`` for all-day events."""

    location: str = ""
    """Free-form location string from the iCalendar record (often empty)."""

    description: str = ""
    """Free-form description / body."""
