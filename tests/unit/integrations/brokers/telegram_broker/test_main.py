"""Tests for integrations.brokers.telegram_broker.__main__ helpers."""

import pytest

from integrations.brokers.telegram_broker.__main__ import _parse_allowed_user_ids


@pytest.mark.unit
class TestParseAllowedUserIds:

    def test_empty_string_yields_empty_set(self):
        assert _parse_allowed_user_ids("") == frozenset()

    def test_whitespace_only_yields_empty_set(self):
        assert _parse_allowed_user_ids("   ,  ,") == frozenset()

    def test_single_id(self):
        assert _parse_allowed_user_ids("12345") == frozenset({12345})

    def test_comma_separated_ids(self):
        assert _parse_allowed_user_ids("1,2,3") == frozenset({1, 2, 3})

    def test_strips_whitespace_around_entries(self):
        assert _parse_allowed_user_ids("  1 ,  2,3  ") == frozenset({1, 2, 3})

    def test_skips_blank_entries(self):
        assert _parse_allowed_user_ids("1,,2,,,3") == frozenset({1, 2, 3})

    def test_skips_non_integer_entries(self, caplog):
        out = _parse_allowed_user_ids("1,bogus,2,also-bad,3")
        assert out == frozenset({1, 2, 3})
        # Confirm we logged each bad entry (presence, not specific text).
        assert any("bogus" in rec.getMessage() for rec in caplog.records)
        assert any("also-bad" in rec.getMessage() for rec in caplog.records)

    def test_deduplicates(self):
        assert _parse_allowed_user_ids("7,7,7,42") == frozenset({7, 42})

    def test_negative_ids_accepted(self):
        # Group chat IDs are negative in Telegram; we don't filter them out
        # at the parser level — that's policy belonging higher up.
        assert _parse_allowed_user_ids("-100,42") == frozenset({-100, 42})
