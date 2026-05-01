"""Unit tests for the calendar tool modules under ``tools.integrations``.

Same pattern as the email-tool tests: stub ``broker_client.call`` to
return canned shapes (or raise) and assert on the resulting plain-text
string. No real CalDAV, no supervisor.
"""

from __future__ import annotations

from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.list_calendars import list_calendars
from tools.integrations.list_events import list_events


def _patch_call(monkeypatch: pytest.MonkeyPatch, *, result: Any = None, exc: Exception | None = None) -> None:
    """Replace ``broker_client.call`` with an async stub."""

    async def _fake(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)


# ── list_calendars ───────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_calendars_renders_each_calendar_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each calendar renders one line: ``- name  —  url``. The url is
    what the agent passes to ``list_events`` to scope a query.
    """
    _patch_call(
        monkeypatch,
        result={"calendars": [
            {"name": "Home", "url": "https://caldav.icloud.com/123/calendars/home/"},
            {"name": "Work", "url": "https://caldav.icloud.com/123/calendars/work/"},
        ]},
    )
    out = await list_calendars("icloud_personal")
    assert out == (
        "Calendars on 'icloud_personal':\n"
        "- Home  —  https://caldav.icloud.com/123/calendars/home/\n"
        "- Work  —  https://caldav.icloud.com/123/calendars/work/"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_calendars_empty_calendars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Account with zero calendars (rare but possible) → single notice line."""
    _patch_call(monkeypatch, result={"calendars": []})
    out = await list_calendars("icloud_personal")
    assert out == "No calendars found on 'icloud_personal'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_calendars_substitutes_placeholder_for_missing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """A calendar without a displayname still renders cleanly; the agent
    can identify it via the URL on the second line.
    """
    _patch_call(
        monkeypatch,
        result={"calendars": [{"url": "https://caldav.icloud.com/123/calendars/x/"}]},
    )
    out = await list_calendars("icloud_personal")
    assert out == (
        "Calendars on 'icloud_personal':\n"
        "- (unnamed)  —  https://caldav.icloud.com/123/calendars/x/"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_calendars_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await list_calendars("icloud_unknown")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_calendars_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await list_calendars("icloud_personal")
    assert out == "Failed to list calendars for 'icloud_personal': upstream boom"


# ── list_events ──────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_renders_with_start_summary_and_location(monkeypatch: pytest.MonkeyPatch) -> None:
    """Events render as ``- start  summary [@ location]`` so the agent can
    scan dates and titles at a glance. The header carries the human-readable
    calendar name (from the broker), not the URL.
    """
    _patch_call(
        monkeypatch,
        result={
            "calendar_name": "Work",
            "events": [
                {
                    "uid": "abc",
                    "summary": "Standup",
                    "start": "2026-04-26T09:00:00+00:00",
                    "end": "2026-04-26T09:15:00+00:00",
                    "location": "Zoom",
                },
                {
                    "uid": "def",
                    "summary": "Lunch",
                    "start": "2026-04-26T12:30:00+00:00",
                    "end": "2026-04-26T13:30:00+00:00",
                },
            ],
        },
    )
    out = await list_events("icloud_personal", "https://caldav.icloud.com/123/calendars/work/")
    assert out == (
        "Events on 'Work' (2):\n"
        "- 2026-04-26T09:00:00+00:00  Standup  @ Zoom\n"
        "- 2026-04-26T12:30:00+00:00  Lunch"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_substitutes_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Events missing summary or start (rare but possible) still render
    parseably so a malformed event doesn't break the whole list.
    """
    _patch_call(monkeypatch, result={"calendar_name": "Home", "events": [{"uid": "x"}]})
    out = await list_events("icloud_personal", "https://x/")
    assert out == (
        "Events on 'Home' (1):\n"
        "- (no start)  (no title)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_empty_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """No events in the queried range → one notice line, names the calendar."""
    _patch_call(monkeypatch, result={"calendar_name": "Home", "events": []})
    out = await list_events("icloud_personal", "https://x/")
    assert out == "No events on 'Home' in this range."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_falls_back_to_url_when_name_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the broker doesn't include ``calendar_name`` (older broker or
    malformed response), the tool falls back to the URL so the agent
    still has *something* to identify the calendar with.
    """
    _patch_call(monkeypatch, result={"events": []})
    out = await list_events("icloud_personal", "https://x/")
    assert out == "No events on 'https://x/' in this range."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_uses_default_date_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults are 30 days forward, 0 days back, limit 50 — verify the
    call carries those values rather than letting the broker pick its own.
    """
    captured: dict[str, Any] = {}

    async def _capture(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        captured["args"] = args
        return {"events": []}

    monkeypatch.setattr(broker_client, "call", _capture)
    await list_events("icloud_personal", "https://x/")
    assert captured["args"]["days_forward"] == 30
    assert captured["args"]["days_back"] == 0
    assert captured["args"]["limit"] == 50


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await list_events("icloud_unknown", "https://x/")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_events_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await list_events("icloud_personal", "https://x/")
    assert out == "Failed to list events for 'icloud_personal': upstream boom"
