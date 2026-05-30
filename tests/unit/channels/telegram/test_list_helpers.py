"""Tests for the /list helpers in channels.telegram._channel."""

from __future__ import annotations

import pytest

from channels.telegram._channel import _matches_query, _row_label
from conversations._models import ConversationSummary


def _summary(
    *,
    conversation_id: str = "telegram_42",
    title: str = "",
    first_message: str = "",
) -> ConversationSummary:
    return ConversationSummary(
        conversation_id=conversation_id,
        title=title,
        first_message=first_message,
        started_at="2026-05-25T00:00:00+00:00",
        turn_count=1,
    )


@pytest.mark.unit
class TestMatchesQuery:

    def test_matches_title_case_insensitive(self):
        s = _summary(title="Trip planning")
        assert _matches_query(s, "trip") is True
        assert _matches_query(s, "TRIP") is True
        assert _matches_query(s, "PLAN") is True

    def test_matches_first_message(self):
        s = _summary(first_message="What's the weather in Paris?")
        assert _matches_query(s, "weather") is True
        assert _matches_query(s, "paris") is True

    def test_no_match(self):
        s = _summary(title="Trip planning", first_message="Looking at flights")
        assert _matches_query(s, "taxes") is False

    def test_empty_fields_do_not_match_arbitrary_query(self):
        s = _summary()
        assert _matches_query(s, "anything") is False


@pytest.mark.unit
class TestRowLabel:

    def test_title_used_when_present(self):
        s = _summary(title="Trip planning")
        assert _row_label(s, is_current=False) == "Trip planning"

    def test_first_message_fallback_when_no_title(self):
        s = _summary(first_message="hello world")
        assert _row_label(s, is_current=False) == "(hello world…)"

    def test_empty_fallback(self):
        s = _summary(conversation_id="telegram_42_x")
        assert _row_label(s, is_current=False) == "(empty • telegram_42_x)"

    def test_current_marker_prepended(self):
        s = _summary(title="Now this one")
        assert _row_label(s, is_current=True) == "✓ Now this one"

    def test_label_clipped_to_telegram_button_safe_length(self):
        s = _summary(title="x" * 200)
        assert len(_row_label(s, is_current=False)) <= 64
        s_current = _summary(title="x" * 200)
        # current adds ✓ and a space; still keeps body to 60 chars.
        assert _row_label(s_current, is_current=True).startswith("✓ ")
