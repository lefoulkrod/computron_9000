"""Unit tests for Google Workspace broker verb helpers."""

from __future__ import annotations

import pytest

from integrations.brokers.google_workspace_broker._verbs import _flatten_event


@pytest.mark.unit
def test_flatten_timed_event() -> None:
    """Timed events use ``start.dateTime``."""
    raw = {
        "id": "abc123",
        "summary": "Standup",
        "start": {"dateTime": "2026-05-05T09:00:00-04:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2026-05-05T09:15:00-04:00", "timeZone": "America/New_York"},
        "location": "Zoom",
    }
    assert _flatten_event(raw) == {
        "uid": "abc123",
        "summary": "Standup",
        "start": "2026-05-05T09:00:00-04:00",
        "end": "2026-05-05T09:15:00-04:00",
        "location": "Zoom",
    }


@pytest.mark.unit
def test_flatten_all_day_event() -> None:
    """All-day events have ``start.date`` instead of ``start.dateTime``."""
    raw = {
        "id": "def456",
        "summary": "Company Holiday",
        "start": {"date": "2026-05-25"},
        "end": {"date": "2026-05-26"},
    }
    assert _flatten_event(raw) == {
        "uid": "def456",
        "summary": "Company Holiday",
        "start": "2026-05-25",
        "end": "2026-05-26",
        "location": "",
    }


@pytest.mark.unit
def test_flatten_minimal_event() -> None:
    """An event missing most fields still produces a complete dict."""
    assert _flatten_event({"id": "x"}) == {
        "uid": "x",
        "summary": "",
        "start": "",
        "end": "",
        "location": "",
    }


@pytest.mark.unit
def test_flatten_prefers_datetime_over_date() -> None:
    """If both ``dateTime`` and ``date`` are present, ``dateTime`` wins."""
    raw = {
        "id": "both",
        "summary": "Edge case",
        "start": {"dateTime": "2026-05-05T10:00:00Z", "date": "2026-05-05"},
        "end": {"dateTime": "2026-05-05T11:00:00Z", "date": "2026-05-05"},
    }
    flat = _flatten_event(raw)
    assert flat["start"] == "2026-05-05T10:00:00Z"
    assert flat["end"] == "2026-05-05T11:00:00Z"
