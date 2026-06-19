"""Tests for integrations.brokers.telegram_broker._verbs.VerbDispatcher."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations._rpc import RpcError
from integrations.brokers.telegram_broker._updates import UpdatePump
from integrations.brokers.telegram_broker._verbs import VerbDispatcher
from integrations.permissions import Access, Capability


_READ_WRITE = {Capability.TELEGRAM: Access.READ_WRITE}
_READ_ONLY = {Capability.TELEGRAM: Access.READ}
_NONE = {Capability.TELEGRAM: Access.OFF}


def _make_pump() -> UpdatePump:
    import pathlib
    return UpdatePump(
        bot=MagicMock(),
        allowed_user_ids=frozenset({1}),
        integration_id="telegram_test",
        downloads_dir=pathlib.Path("/tmp"),
    )


def _make_dispatcher(*, permissions=_READ_WRITE, bot=None, pump=None) -> VerbDispatcher:
    return VerbDispatcher(
        bot=bot or MagicMock(),
        pump=pump or _make_pump(),
        permissions=permissions,
    )


# ---------------------------------------------------------------------------
# Verb gating
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchGating:

    async def test_unknown_verb_raises_bad_request(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("nope", {})
        assert exc.value.code == "BAD_REQUEST"

    async def test_insufficient_access_raises_permission_denied(self):
        dispatcher = _make_dispatcher(permissions=_READ_ONLY)
        # send_message requires READ_WRITE.
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("send_message", {"chat_id": 1, "text": "x"})
        assert exc.value.code == "PERMISSION_DENIED"

    async def test_off_capability_blocks_read_verbs_too(self):
        dispatcher = _make_dispatcher(permissions=_NONE)
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("get_me", {})
        assert exc.value.code == "PERMISSION_DENIED"

    async def test_write_verb_blocked_by_permission_gate(self):
        # The permission gate must fire before any handler logic runs.
        dispatcher = _make_dispatcher(permissions=_READ_ONLY)
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch(
                "send_document", {"chat_id": 1, "host_path": "/tmp/whatever"},
            )
        assert exc.value.code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# get_me
# ---------------------------------------------------------------------------


@dataclass
class _FakeMe:
    id: int
    username: str | None
    first_name: str


@pytest.mark.unit
class TestGetMe:

    async def test_returns_identity_fields(self):
        bot = MagicMock()
        bot.get_me = AsyncMock(return_value=_FakeMe(id=42, username="testbot", first_name="Test"))
        dispatcher = _make_dispatcher(bot=bot)
        out = await dispatcher.dispatch("get_me", {})
        assert out == {"id": 42, "username": "testbot", "first_name": "Test"}


# ---------------------------------------------------------------------------
# next_updates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNextUpdates:

    async def test_returns_empty_on_timeout(self):
        pump = _make_pump()
        dispatcher = _make_dispatcher(pump=pump)
        out = await dispatcher.dispatch("next_updates", {"timeout_ms": 50})
        assert out == {"updates": []}

    async def test_drains_buffered_batch(self):
        pump = _make_pump()
        pump.queue.put_nowait({"type": "message", "text": "a", "message_id": 1})
        pump.queue.put_nowait({"type": "message", "text": "b", "message_id": 2})
        pump.queue.put_nowait({"type": "message", "text": "c", "message_id": 3})
        dispatcher = _make_dispatcher(pump=pump)
        out = await dispatcher.dispatch("next_updates", {"timeout_ms": 50})
        assert [u["text"] for u in out["updates"]] == ["a", "b", "c"]
        assert pump.queue.empty()

    async def test_blocks_until_an_update_arrives(self):
        """The handler waits up to timeout_ms for the first update."""
        pump = _make_pump()
        dispatcher = _make_dispatcher(pump=pump)

        async def _deliver_later() -> None:
            await asyncio.sleep(0.02)
            pump.queue.put_nowait({"type": "message", "text": "late", "message_id": 1})

        deliver_task = asyncio.create_task(_deliver_later())
        out = await dispatcher.dispatch("next_updates", {"timeout_ms": 1000})
        await deliver_task
        assert len(out["updates"]) == 1
        assert out["updates"][0]["text"] == "late"

    async def test_rejects_negative_timeout(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("next_updates", {"timeout_ms": -1})
        assert exc.value.code == "BAD_REQUEST"

    async def test_default_timeout_used_when_missing(self):
        pump = _make_pump()
        pump.queue.put_nowait({"type": "message", "text": "x", "message_id": 1})
        dispatcher = _make_dispatcher(pump=pump)
        out = await dispatcher.dispatch("next_updates", {})
        # With an item ready the handler returns immediately regardless of
        # default timeout — assert the item came through.
        assert len(out["updates"]) == 1


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


@dataclass
class _FakeSentMessage:
    message_id: int


@pytest.mark.unit
class TestSendMessage:

    async def test_sends_and_returns_message_id(self):
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=_FakeSentMessage(message_id=777))
        dispatcher = _make_dispatcher(bot=bot)
        out = await dispatcher.dispatch(
            "send_message", {"chat_id": 42, "text": "hi"},
        )
        assert out == {"message_id": 777}
        bot.send_message.assert_awaited_once_with(
            chat_id=42,
            text="hi",
            reply_to_message_id=None,
            reply_markup=None,
            parse_mode=None,
        )

    async def test_passes_parse_mode_when_provided(self):
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=_FakeSentMessage(message_id=1))
        dispatcher = _make_dispatcher(bot=bot)
        await dispatcher.dispatch(
            "send_message",
            {"chat_id": 1, "text": "hi", "parse_mode": "MarkdownV2"},
        )
        assert bot.send_message.await_args.kwargs["parse_mode"] == "MarkdownV2"

    async def test_rejects_non_string_parse_mode(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch(
                "send_message",
                {"chat_id": 1, "text": "hi", "parse_mode": 42},
            )
        assert exc.value.code == "BAD_REQUEST"

    async def test_passes_reply_to_message_id_when_provided(self):
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=_FakeSentMessage(message_id=1))
        dispatcher = _make_dispatcher(bot=bot)
        await dispatcher.dispatch(
            "send_message",
            {"chat_id": 1, "text": "hi", "reply_to_message_id": 5},
        )
        assert bot.send_message.await_args.kwargs["reply_to_message_id"] == 5

    @pytest.mark.parametrize("bad_chat_id", [None, "42", 1.5, True, False])
    async def test_rejects_non_integer_chat_id(self, bad_chat_id):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("send_message", {"chat_id": bad_chat_id, "text": "hi"})
        assert exc.value.code == "BAD_REQUEST"

    @pytest.mark.parametrize("bad_text", [None, "", 0, []])
    async def test_rejects_empty_or_non_string_text(self, bad_text):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("send_message", {"chat_id": 1, "text": bad_text})
        assert exc.value.code == "BAD_REQUEST"

    async def test_rejects_non_integer_reply_to(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch(
                "send_message",
                {"chat_id": 1, "text": "hi", "reply_to_message_id": "5"},
            )
        assert exc.value.code == "BAD_REQUEST"

    async def test_aiogram_api_error_becomes_internal_rpc_error(self):
        from aiogram.exceptions import TelegramBadRequest

        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=TelegramBadRequest(
            method=MagicMock(), message="chat not found",
        ))
        dispatcher = _make_dispatcher(bot=bot)
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("send_message", {"chat_id": 1, "text": "hi"})
        assert exc.value.code == "INTERNAL"

    async def test_passes_inline_keyboard_when_buttons_provided(self):
        from aiogram.types import InlineKeyboardMarkup

        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=_FakeSentMessage(message_id=1))
        dispatcher = _make_dispatcher(bot=bot)
        await dispatcher.dispatch(
            "send_message",
            {
                "chat_id": 1,
                "text": "Pick:",
                "buttons": [
                    [{"text": "A", "data": "a"}, {"text": "B", "data": "b"}],
                    [{"text": "C", "data": "c"}],
                ],
            },
        )
        markup = bot.send_message.await_args.kwargs["reply_markup"]
        assert isinstance(markup, InlineKeyboardMarkup)
        # Two rows; first has two buttons, second has one.
        assert [len(row) for row in markup.inline_keyboard] == [2, 1]
        assert markup.inline_keyboard[0][0].text == "A"
        assert markup.inline_keyboard[0][0].callback_data == "a"
        assert markup.inline_keyboard[1][0].callback_data == "c"

    @pytest.mark.parametrize("bad_buttons", [
        "not a list",
        [{"not": "a list"}],          # row isn't a list
        [[{"text": "a"}]],            # missing data
        [[{"data": "x"}]],            # missing text
        [[{"text": "", "data": "x"}]],  # empty text
        [[{"text": "a", "data": ""}]],  # empty data
    ])
    async def test_rejects_malformed_buttons(self, bad_buttons):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch(
                "send_message", {"chat_id": 1, "text": "x", "buttons": bad_buttons},
            )
        assert exc.value.code == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# send_chat_action
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendChatAction:

    async def test_calls_bot_send_chat_action(self):
        bot = MagicMock()
        bot.send_chat_action = AsyncMock()
        dispatcher = _make_dispatcher(bot=bot)
        out = await dispatcher.dispatch(
            "send_chat_action", {"chat_id": 7, "action": "typing"},
        )
        assert out == {}
        bot.send_chat_action.assert_awaited_once_with(chat_id=7, action="typing")

    async def test_requires_action(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("send_chat_action", {"chat_id": 7})
        assert exc.value.code == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# answer_callback_query
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnswerCallbackQuery:

    async def test_calls_bot_answer(self):
        bot = MagicMock()
        bot.answer_callback_query = AsyncMock()
        dispatcher = _make_dispatcher(bot=bot)
        await dispatcher.dispatch(
            "answer_callback_query",
            {"callback_id": "cbq-1", "text": "Picked!"},
        )
        bot.answer_callback_query.assert_awaited_once_with(
            callback_query_id="cbq-1", text="Picked!",
        )

    async def test_text_optional(self):
        bot = MagicMock()
        bot.answer_callback_query = AsyncMock()
        dispatcher = _make_dispatcher(bot=bot)
        await dispatcher.dispatch(
            "answer_callback_query", {"callback_id": "cbq-1"},
        )
        bot.answer_callback_query.assert_awaited_once_with(
            callback_query_id="cbq-1", text=None,
        )


# ---------------------------------------------------------------------------
# send_document
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendDocument:

    async def test_sends_existing_file(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"hello")

        bot = MagicMock()
        bot.send_document = AsyncMock(return_value=_FakeSentMessage(message_id=99))
        dispatcher = _make_dispatcher(bot=bot)

        out = await dispatcher.dispatch(
            "send_document",
            {"chat_id": 1, "host_path": str(f), "caption": "📎 report.pdf"},
        )
        assert out == {"message_id": 99}
        kwargs = bot.send_document.await_args.kwargs
        assert kwargs["chat_id"] == 1
        assert kwargs["caption"] == "📎 report.pdf"
        # The document arg is an FSInputFile pointing at the host path.
        assert kwargs["document"].path == str(f)

    async def test_missing_file_rejected(self):
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch(
                "send_document", {"chat_id": 1, "host_path": "/no/such/file.bin"},
            )
        assert exc.value.code == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# edit_message_text + delete_message — live status message support
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEditMessageText:

    async def test_calls_bot_edit(self):
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        dispatcher = _make_dispatcher(bot=bot)
        out = await dispatcher.dispatch(
            "edit_message_text",
            {"chat_id": 7, "message_id": 100, "text": "🔧 Calling search..."},
        )
        assert out == {}
        bot.edit_message_text.assert_awaited_once_with(
            chat_id=7, message_id=100, text="🔧 Calling search...",
        )

    @pytest.mark.parametrize("missing", ["chat_id", "message_id", "text"])
    async def test_required_args(self, missing):
        args = {"chat_id": 1, "message_id": 2, "text": "x"}
        args.pop(missing)
        dispatcher = _make_dispatcher()
        with pytest.raises(RpcError) as exc:
            await dispatcher.dispatch("edit_message_text", args)
        assert exc.value.code == "BAD_REQUEST"


@pytest.mark.unit
class TestDeleteMessage:

    async def test_calls_bot_delete(self):
        bot = MagicMock()
        bot.delete_message = AsyncMock()
        dispatcher = _make_dispatcher(bot=bot)
        out = await dispatcher.dispatch(
            "delete_message", {"chat_id": 7, "message_id": 100},
        )
        assert out == {}
        bot.delete_message.assert_awaited_once_with(chat_id=7, message_id=100)
