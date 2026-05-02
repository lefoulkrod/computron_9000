"""Public read/write classification for email/calendar and storage verbs.

This is the app-server side of the same vocabulary the brokers enforce in
``brokers/email_broker/_verbs._VERB_TYPE`` and
``brokers/rclone_broker/_verbs._VERB_TYPE``. Two reasons for keeping a copy
on this side rather than reaching across the package boundary:

- The app server may want to short-circuit a write call before the broker
  hop — e.g. surfacing "writes disabled for this integration" without a
  socket round-trip. Keeping a local table makes that cheap.
- It documents the public contract of what verbs the broker_client expects
  to be able to call. The brokers remain the authoritative gate; this
  table is advisory.

A unit test (``tests/integrations/test_verb_types_drift.py``) asserts
this dict stays equal to the union of all broker verb dicts. Adding a verb
on one side without the other fails that test loudly.
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
    "move_messages": "write",
    "send_message": "write",
    # Calendar (CalDAV)
    "list_calendars": "read",
    "list_events": "read",
    "create_event": "write",
    "delete_event": "write",
    # Storage (rclone)
    "list_directory": "read",
    "about": "read",
    "search": "read",
    "cat": "read",
    "size": "read",
    "copy_from_remote": "read",
    "copy_to_remote": "write",
    "move_from_remote": "write",
    "move_to_remote": "write",
    "delete": "write",
    "mkdir": "write",
}

_VERB_CAPABILITY: dict[str, str] = {
    "list_mailboxes": "email_calendar",
    "search_messages": "email_calendar",
    "fetch_message": "email_calendar",
    "list_messages": "email_calendar",
    "fetch_attachment": "email_calendar",
    "move_messages": "email_calendar",
    "send_message": "email_calendar",
    "list_calendars": "email_calendar",
    "list_events": "email_calendar",
    "create_event": "email_calendar",
    "delete_event": "email_calendar",
    # Storage (rclone)
    "list_directory": "storage",
    "about": "storage",
    "search": "storage",
    "cat": "storage",
    "size": "storage",
    "copy_from_remote": "storage",
    "copy_to_remote": "storage",
    "move_from_remote": "storage",
    "move_to_remote": "storage",
    "delete": "storage",
    "mkdir": "storage",
}
