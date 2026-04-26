"""Public read/write classification for email-broker verbs.

This is the app-server side of the same vocabulary the broker enforces in
``brokers/email_broker/_verbs._VERB_TYPE``. Two reasons for keeping a copy
on this side rather than reaching across the package boundary:

- The app server may want to short-circuit a write call before the broker
  hop — e.g. surfacing "writes disabled for this integration" without a
  socket round-trip. Keeping a local table makes that cheap.
- It documents the public contract of what verbs the broker_client expects
  to be able to call. The broker remains the authoritative gate; this
  table is advisory.

A unit test (``tests/integrations/test_verb_types_drift.py``) asserts
this dict stays equal to the broker's. Adding a verb on one side without
the other fails that test loudly.
"""

from __future__ import annotations

from typing import Literal

_VERB_TYPES: dict[str, Literal["read", "write"]] = {
    # Email
    "list_mailboxes": "read",
    "search_messages": "read",
    "fetch_message": "read",
    "list_messages": "read",
    "fetch_attachment": "read",
    "move_message": "write",
    "send_message": "write",
    # Calendar (CalDAV)
    "list_calendars": "read",
    "list_events": "read",
    "create_event": "write",
    "delete_event": "write",
}
