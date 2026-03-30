"""Cron evaluation for recurring goals."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

from croniter import croniter


def cron_has_fired_since(cron_expr: str, anchor: str, tz_name: str = "UTC") -> bool:
    """Return True if the cron expression has fired since the anchor time.

    Args:
        cron_expr: A standard cron expression (e.g. ``"0 */2 * * *"``).
        anchor: ISO 8601 UTC timestamp to check from.
        tz_name: IANA timezone name (e.g., "America/Chicago", "UTC").

    Returns:
        True if the next fire time after *anchor* is in the past.
    """
    # Validate and get timezone
    tz = ZoneInfo(tz_name) if tz_name in available_timezones() else ZoneInfo("UTC")
    
    # Parse anchor as UTC, then convert to target timezone
    anchor_dt = datetime.fromisoformat(anchor)
    if anchor_dt.tzinfo is None:
        anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
    anchor_local = anchor_dt.astimezone(tz)
    
    # Evaluate cron in local timezone
    cron = croniter(cron_expr, anchor_local)
    next_fire = cron.get_next(datetime)
    
    # Ensure next_fire has timezone info
    if next_fire.tzinfo is None:
        next_fire = next_fire.replace(tzinfo=tz)
    
    # Convert back to UTC for comparison
    next_fire_utc = next_fire.astimezone(timezone.utc)
    
    return next_fire_utc <= datetime.now(timezone.utc)


__all__ = ["cron_has_fired_since"]
