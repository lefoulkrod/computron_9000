"""Tests for tasks._scheduler."""

from datetime import datetime, timedelta, timezone

import pytest

from tasks._scheduler import cron_has_fired_since


@pytest.mark.unit
class TestCronHasFiredSince:
    """Test cron evaluation logic."""

    def test_fired_recently(self):
        """A minutely cron should have fired since 5 minutes ago."""
        anchor = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert cron_has_fired_since("* * * * *", anchor) is True

    def test_not_fired_yet(self):
        """A yearly cron should not have fired since just now."""
        anchor = datetime.now(timezone.utc).isoformat()
        # "0 0 1 1 *" = midnight Jan 1 — won't fire within seconds
        assert cron_has_fired_since("0 0 1 1 *", anchor) is False

    def test_hourly_cron_past_anchor(self):
        """Hourly cron with anchor 2 hours ago should be due."""
        anchor = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert cron_has_fired_since("0 * * * *", anchor) is True

    def test_anchor_without_timezone(self):
        """Anchor without timezone info is treated as UTC."""
        anchor = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        assert cron_has_fired_since("* * * * *", anchor) is True
