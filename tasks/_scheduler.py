"""Cron evaluation for recurring goals."""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter


def cron_has_fired_since(cron_expr: str, anchor: str) -> bool:
    """Return True if the cron expression has fired since the anchor time.

    Args:
        cron_expr: A standard cron expression (e.g. ``"0 */2 * * *"``).
        anchor: ISO 8601 UTC timestamp to check from.

    Returns:
        True if the next fire time after *anchor* is in the past.
    """
    anchor_dt = datetime.fromisoformat(anchor)
    if anchor_dt.tzinfo is None:
        anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
    cron = croniter(cron_expr, anchor_dt)
    next_fire = cron.get_next(datetime)
    if next_fire.tzinfo is None:
        next_fire = next_fire.replace(tzinfo=timezone.utc)
    return next_fire <= datetime.now(timezone.utc)


__all__ = ["cron_has_fired_since"]
