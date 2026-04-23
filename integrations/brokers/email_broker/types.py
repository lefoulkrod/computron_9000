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
