"""Tests for integrations.brokers.telegram_broker._updates."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from integrations.brokers.telegram_broker._updates import (
    UpdatePump,
    update_to_dict,
)


# ---------------------------------------------------------------------------
# Fake update objects — shape matches the aiogram attributes we read.
# ---------------------------------------------------------------------------


@dataclass
class _FakeUser:
    id: int
    username: str | None = None


@dataclass
class _FakeChat:
    id: int


@dataclass
class _FakeMessage:
    message_id: int
    chat: _FakeChat
    from_user: _FakeUser | None
    text: str | None
    date: datetime | None = field(default_factory=lambda: datetime(2026, 5, 22, tzinfo=timezone.utc))


@dataclass
class _FakeCallbackQuery:
    id: str
    from_user: _FakeUser | None
    data: str | None
    message: _FakeMessage | None


@dataclass
class _FakeUpdate:
    update_id: int
    message: _FakeMessage | None = None
    callback_query: _FakeCallbackQuery | None = None


# ---------------------------------------------------------------------------
# update_to_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateToDict:

    def test_text_message_maps_to_wire_dict(self):
        msg = _FakeMessage(
            message_id=10,
            chat=_FakeChat(id=42),
            from_user=_FakeUser(id=99, username="alice"),
            text="hello",
        )
        out = update_to_dict(_FakeUpdate(update_id=1, message=msg))
        assert out is not None
        assert out["type"] == "message"
        assert out["message_id"] == 10
        assert out["chat_id"] == 42
        assert out["from_user_id"] == 99
        assert out["from_username"] == "alice"
        assert out["text"] == "hello"
        assert out["is_command"] is False
        assert isinstance(out["timestamp"], int)

    def test_slash_text_marked_as_command(self):
        msg = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=_FakeUser(id=1), text="/new",
        )
        out = update_to_dict(_FakeUpdate(update_id=1, message=msg))
        assert out is not None
        assert out["is_command"] is True

    def test_no_message_returns_none(self):
        # Update without a message field (e.g. a callback_query in real Telegram).
        out = update_to_dict(_FakeUpdate(update_id=1, message=None))
        assert out is None

    def test_message_without_text_returns_none(self):
        # Photo/document/sticker — no .text, dropped at this layer.
        msg = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=_FakeUser(id=1), text=None,
        )
        assert update_to_dict(_FakeUpdate(update_id=1, message=msg)) is None

    def test_message_without_from_user_returns_none(self):
        # Service messages (channel posts, etc.) can lack from_user.
        msg = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=None, text="hi",
        )
        assert update_to_dict(_FakeUpdate(update_id=1, message=msg)) is None

    def test_falls_back_to_now_when_no_date(self):
        msg = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=_FakeUser(id=1), text="hi", date=None,
        )
        before = int(time.time())
        out = update_to_dict(_FakeUpdate(update_id=1, message=msg))
        after = int(time.time())
        assert out is not None
        assert before <= out["timestamp"] <= after

    def test_callback_query_maps_to_wire_dict(self):
        carrier_msg = _FakeMessage(
            message_id=200, chat=_FakeChat(id=42),
            from_user=_FakeUser(id=99), text="Pick:",
        )
        cb = _FakeCallbackQuery(
            id="cbq-1",
            from_user=_FakeUser(id=99, username="alice"),
            data="profile:foo",
            message=carrier_msg,
        )
        out = update_to_dict(_FakeUpdate(update_id=1, callback_query=cb))
        assert out is not None
        assert out["type"] == "callback_query"
        assert out["callback_id"] == "cbq-1"
        assert out["from_user_id"] == 99
        assert out["from_username"] == "alice"
        assert out["data"] == "profile:foo"
        assert out["chat_id"] == 42
        assert out["message_id"] == 200

    def test_callback_without_from_user_is_dropped(self):
        carrier = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=_FakeUser(id=1), text="x",
        )
        cb = _FakeCallbackQuery(id="x", from_user=None, data="d", message=carrier)
        assert update_to_dict(_FakeUpdate(update_id=1, callback_query=cb)) is None

    def test_callback_without_data_is_dropped(self):
        carrier = _FakeMessage(
            message_id=1, chat=_FakeChat(id=1),
            from_user=_FakeUser(id=1), text="x",
        )
        cb = _FakeCallbackQuery(
            id="x", from_user=_FakeUser(id=1), data=None, message=carrier,
        )
        assert update_to_dict(_FakeUpdate(update_id=1, callback_query=cb)) is None

    def test_callback_without_carrier_message_is_dropped(self):
        cb = _FakeCallbackQuery(
            id="x", from_user=_FakeUser(id=1), data="d", message=None,
        )
        assert update_to_dict(_FakeUpdate(update_id=1, callback_query=cb)) is None


# ---------------------------------------------------------------------------
# UpdatePump._handle_update — the security filter
# ---------------------------------------------------------------------------


def _make_pump(allowed_ids: frozenset[int], *, downloads_dir=None) -> UpdatePump:
    """UpdatePump with a stubbed Bot — _handle_update doesn't use the bot."""
    return UpdatePump(
        bot=MagicMock(),
        allowed_user_ids=allowed_ids,
        integration_id="telegram_test",
        downloads_dir=downloads_dir or __import__("pathlib").Path("/tmp"),
    )


def _msg_update(*, user_id: int, text: str = "hi", update_id: int = 1) -> _FakeUpdate:
    return _FakeUpdate(
        update_id=update_id,
        message=_FakeMessage(
            message_id=update_id,
            chat=_FakeChat(id=user_id),  # DM: chat.id == user.id
            from_user=_FakeUser(id=user_id),
            text=text,
        ),
    )


@pytest.mark.unit
class TestUpdatePumpFilter:

    async def test_allowed_user_is_enqueued(self):
        pump = _make_pump(frozenset({100}))
        await pump._handle_update(_msg_update(user_id=100, text="hello"))
        assert pump.queue.qsize() == 1
        out = pump.queue.get_nowait()
        assert out["from_user_id"] == 100
        assert out["text"] == "hello"

    async def test_disallowed_user_is_dropped(self):
        pump = _make_pump(frozenset({100}))
        await pump._handle_update(_msg_update(user_id=999, text="spam"))
        assert pump.queue.qsize() == 0
        # Drop accounted for.
        assert pump._drop_counts == {999: 1}

    async def test_disallowed_drops_accumulate_per_user(self):
        pump = _make_pump(frozenset({100}))
        for i in range(3):
            await pump._handle_update(
                _msg_update(user_id=999, text=f"spam{i}", update_id=i),
            )
        for i in range(2):
            await pump._handle_update(
                _msg_update(user_id=888, text=f"x{i}", update_id=100 + i),
            )
        assert pump.queue.qsize() == 0
        assert pump._drop_counts == {999: 3, 888: 2}

    async def test_skippable_update_is_neither_queued_nor_counted(self):
        # No-message update — update_to_dict returns None and the filter
        # path is bypassed entirely. Drops counter must not bump.
        pump = _make_pump(frozenset({100}))
        await pump._handle_update(_FakeUpdate(update_id=1, message=None))
        assert pump.queue.qsize() == 0
        assert pump._drop_counts == {}

    async def test_empty_allowlist_drops_everyone(self):
        pump = _make_pump(frozenset())
        await pump._handle_update(_msg_update(user_id=1))
        await pump._handle_update(_msg_update(user_id=2))
        assert pump.queue.qsize() == 0
        assert sum(pump._drop_counts.values()) == 2


@pytest.mark.unit
class TestUpdatePumpDropLog:

    async def test_drop_log_does_not_flush_within_window(self, caplog):
        pump = _make_pump(frozenset({100}))
        await pump._handle_update(_msg_update(user_id=999))
        # Calling flush immediately (window not elapsed) should not log
        # and should leave the counter intact.
        pump._maybe_flush_drop_log()
        assert pump._drop_counts == {999: 1}

    async def test_drop_log_flushes_and_resets_after_window(self, caplog, monkeypatch):
        pump = _make_pump(frozenset({100}))
        await pump._handle_update(_msg_update(user_id=999))
        await pump._handle_update(_msg_update(user_id=888))

        # Pretend the window started 9999 seconds ago so the flush fires.
        pump._drop_window_started_at = time.monotonic() - 9999.0

        with caplog.at_level("WARNING"):
            pump._maybe_flush_drop_log()

        # Drop counters cleared, a log line emitted per offender.
        assert pump._drop_counts == {}
        messages = " ".join(rec.getMessage() for rec in caplog.records)
        assert "user_id=999" in messages
        assert "user_id=888" in messages

    def test_drop_log_no_op_when_nothing_to_flush(self, caplog):
        pump = _make_pump(frozenset({100}))
        pump._drop_window_started_at = time.monotonic() - 9999.0
        with caplog.at_level("WARNING"):
            pump._maybe_flush_drop_log()
        # Window timer should still reset even if there was nothing to log.
        assert pump._drop_counts == {}
