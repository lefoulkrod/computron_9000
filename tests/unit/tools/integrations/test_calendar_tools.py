"""Unit tests for the calendar tool modules under ``tools.integrations``.

Same pattern as the email-tool tests: stub ``broker_client.call`` to
return canned shapes (or raise) and assert on the resulting plain-text
string. No real CalDAV, no supervisor.
"""

from __future__ import annotations

from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.create_event import create_event
from tools.integrations.delete_event import delete_event
from tools.integrations.list_calendars import list_calendars
from tools.integrations.list_events import list_events
from tools.integrations.update_event import update_event


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
        "- 2026-04-26T09:00:00+00:00  Standup  @ Zoom  [id: abc]\n"
        "- 2026-04-26T12:30:00+00:00  Lunch  [id: def]"
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
        "- (no start)  (no title)  [id: x]"
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


# ── create_event ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_confirms_with_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "event": {
            "uid": "ev_abc123",
            "summary": "Team standup",
            "start": "2026-05-10T09:00:00-05:00",
            "end": "2026-05-10T09:30:00-05:00",
            "location": "",
        },
    })
    out = await create_event(
        "gw_work", "primary", "Team standup",
        "2026-05-10T09:00:00-05:00", "2026-05-10T09:30:00-05:00",
    )
    assert "ev_abc123" in out
    assert "Team standup" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_passes_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"event": {"uid": "x", "summary": "s", "start": "", "end": "", "location": ""}}

    monkeypatch.setattr(broker_client, "call", _capture)

    await create_event(
        "gw_work", "primary", "Lunch",
        "2026-05-10T12:00:00Z", "2026-05-10T13:00:00Z",
        description="Team lunch",
        location="Cafeteria",
        attendees=["alice@example.com", "bob@example.com"],
    )
    assert captured["description"] == "Team lunch"
    assert captured["location"] == "Cafeteria"
    assert captured["attendees"] == ["alice@example.com", "bob@example.com"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_omits_empty_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"event": {"uid": "x", "summary": "s", "start": "", "end": "", "location": ""}}

    monkeypatch.setattr(broker_client, "call", _capture)

    await create_event(
        "gw_work", "primary", "Quick sync",
        "2026-05-10T14:00:00Z", "2026-05-10T14:30:00Z",
    )
    assert "description" not in captured
    assert "location" not in captured
    assert "attendees" not in captured


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("gw_work"))
    out = await create_event(
        "gw_work", "primary", "Meeting",
        "2026-05-10T09:00:00Z", "2026-05-10T10:00:00Z",
    )
    assert "not connected" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_write_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("gw_work"))
    out = await create_event(
        "gw_work", "primary", "Meeting",
        "2026-05-10T09:00:00Z", "2026-05-10T10:00:00Z",
    )
    assert "disabled" in out.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_event_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("quota exceeded"))
    out = await create_event(
        "gw_work", "primary", "Meeting",
        "2026-05-10T09:00:00Z", "2026-05-10T10:00:00Z",
    )
    assert "Failed" in out


# ── update_event ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_confirms_with_title(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={
        "event": {
            "uid": "ev_abc123",
            "summary": "Updated standup",
            "start": "2026-05-10T09:00:00-05:00",
            "end": "2026-05-10T09:30:00-05:00",
            "location": "",
        },
    })
    out = await update_event(
        "gw_work", "primary", "ev_abc123", summary="Updated standup",
    )
    assert "Updated standup" in out
    assert "ev_abc123" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_passes_only_provided_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"event": {"uid": "ev1", "summary": "x", "start": "", "end": "", "location": ""}}

    monkeypatch.setattr(broker_client, "call", _capture)

    await update_event("gw_work", "primary", "ev1", location="Room 42")
    assert captured["location"] == "Room 42"
    assert "summary" not in captured
    assert "start" not in captured
    assert "attendees" not in captured


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_no_fields_returns_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={})
    out = await update_event("gw_work", "primary", "ev1")
    assert "No fields" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("gw_work"))
    out = await update_event("gw_work", "primary", "ev1", summary="Changed")
    assert "not connected" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_write_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("gw_work"))
    out = await update_event("gw_work", "primary", "ev1", summary="Changed")
    assert "disabled" in out.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_event_attendees(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _capture(
        integration_id: str, verb: str, args: dict, *, app_sock_path: str,
    ) -> Any:
        captured.update(args)
        return {"event": {"uid": "ev1", "summary": "x", "start": "", "end": "", "location": ""}}

    monkeypatch.setattr(broker_client, "call", _capture)

    await update_event("gw_work", "primary", "ev1", attendees=["alice@example.com"])
    assert captured["attendees"] == ["alice@example.com"]


# ── delete_event ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_event_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"deleted": True})
    out = await delete_event("gw_work", "primary", "ev_abc123")
    assert "Deleted" in out
    assert "ev_abc123" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_event_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("gw_work"))
    out = await delete_event("gw_work", "primary", "ev1")
    assert "not connected" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_event_write_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("gw_work"))
    out = await delete_event("gw_work", "primary", "ev1")
    assert "disabled" in out.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_event_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("not found"))
    out = await delete_event("gw_work", "primary", "ev1")
    assert "Failed" in out
