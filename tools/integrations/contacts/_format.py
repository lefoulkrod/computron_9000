"""Shared formatting for contact tool output."""

from __future__ import annotations

from typing import Any


def format_contact(c: dict[str, Any]) -> str:
    """Format one contact as a single line for agent output."""
    emails = c.get("emails", [])
    name = c.get("name") or (emails[0] if emails else "(unnamed)")
    parts = [f"- {name}"]

    for email in emails:
        parts.append(f"  <{email}>")

    phones = c.get("phones", [])
    for phone in phones:
        parts.append(f"  {phone}")

    org = c.get("organization", "")
    title = c.get("title", "")
    if org and title:
        parts.append(f"  ({title} @ {org})")
    elif org:
        parts.append(f"  ({org})")
    elif title:
        parts.append(f"  ({title})")

    return "".join(parts)
