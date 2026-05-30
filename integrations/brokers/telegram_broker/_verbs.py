"""Verb dispatcher for the telegram broker.

Bridges the RPC frame layer to aiogram's typed Bot methods. Same shape as
the email broker's dispatcher: a ``_VERB_REQUIREMENT`` table gates each
verb by ``(Capability, min Access)``, and the handler table is allowed
to omit verbs that haven't been implemented yet — those return BAD_REQUEST.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from integrations._rpc import RpcError
from integrations.brokers.telegram_broker._updates import UpdatePump
from integrations.permissions import Access, Capability, Permissions

# Per-verb: (capability, minimum_access_required).
_VERB_REQUIREMENT: dict[str, tuple[Capability, Access]] = {
    "get_me": (Capability.TELEGRAM, Access.READ),
    "next_updates": (Capability.TELEGRAM, Access.READ),
    "send_message": (Capability.TELEGRAM, Access.READ_WRITE),
    "send_document": (Capability.TELEGRAM, Access.READ_WRITE),
    "send_chat_action": (Capability.TELEGRAM, Access.READ_WRITE),
    "answer_callback_query": (Capability.TELEGRAM, Access.READ_WRITE),
    "edit_message_text": (Capability.TELEGRAM, Access.READ_WRITE),
    "delete_message": (Capability.TELEGRAM, Access.READ_WRITE),
}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right Bot method."""

    def __init__(
        self,
        bot: Bot,
        pump: UpdatePump,
        *,
        permissions: Permissions,
    ) -> None:
        self._bot = bot
        self._pump = pump
        self._permissions = permissions
        self._handlers: dict[str, _Handler] = {
            "get_me": self._handle_get_me,
            "next_updates": self._handle_next_updates,
            "send_message": self._handle_send_message,
            "send_document": self._handle_send_document,
            "send_chat_action": self._handle_send_chat_action,
            "answer_callback_query": self._handle_answer_callback_query,
            "edit_message_text": self._handle_edit_message_text,
            "delete_message": self._handle_delete_message,
        }

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        requirement = _VERB_REQUIREMENT.get(verb)
        if requirement is None:
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        cap, min_access = requirement
        granted = self._permissions.get(cap, Access.OFF)
        if granted < min_access:
            msg = (
                f"verb {verb!r} requires {cap.value}:{min_access.name.lower()}, "
                f"but this integration has {cap.value}:{granted.name.lower()}"
            )
            raise RpcError("PERMISSION_DENIED", msg)

        handler = self._handlers.get(verb)
        if handler is None:
            msg = f"verb not implemented: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        return await handler(args)

    # --- handlers -----------------------------------------------------------

    async def _handle_get_me(self, _args: dict[str, Any]) -> dict[str, Any]:
        """``get_me`` → ``{id, username, first_name}``."""
        try:
            me = await self._bot.get_me()
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }

    async def _handle_next_updates(self, args: dict[str, Any]) -> dict[str, Any]:
        """``next_updates {timeout_ms}`` → ``{updates: [...]}``.

        Long-polls the internal queue: blocks up to ``timeout_ms`` for the
        first update, then drains everything currently buffered before
        returning. Empty list on timeout.
        """
        timeout_ms = _require_int(args, "timeout_ms", default=25_000)
        if timeout_ms < 0:
            raise RpcError("BAD_REQUEST", "'timeout_ms' must be >= 0")
        timeout_s = timeout_ms / 1000.0

        updates: list[dict[str, Any]] = []
        try:
            first = await asyncio.wait_for(self._pump.queue.get(), timeout=timeout_s)
            updates.append(first)
        except asyncio.TimeoutError:
            return {"updates": []}

        # Drain the rest without blocking so the caller gets a full batch.
        while True:
            try:
                updates.append(self._pump.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return {"updates": updates}

    async def _handle_send_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """``send_message {chat_id, text, reply_to_message_id?, buttons?, parse_mode?}`` → ``{message_id}``.

        ``buttons`` is an optional 2-D array of ``{text, data}`` dicts that
        becomes an inline keyboard attached to the message. Each tap fires a
        callback_query update with ``data`` matching what was sent.

        ``parse_mode`` is an optional Telegram parse-mode string
        (``"MarkdownV2"``, ``"HTML"``, ``"Markdown"``). Omit for plain text.
        """
        chat_id = _require_int(args, "chat_id")
        text = _require_str(args, "text")
        reply_to = args.get("reply_to_message_id")
        if reply_to is not None and (isinstance(reply_to, bool) or not isinstance(reply_to, int)):
            raise RpcError("BAD_REQUEST", "'reply_to_message_id' must be an integer")
        parse_mode = args.get("parse_mode")
        if parse_mode is not None and not isinstance(parse_mode, str):
            raise RpcError("BAD_REQUEST", "'parse_mode' must be a string")
        reply_markup = _coerce_inline_keyboard(args.get("buttons"))
        try:
            msg = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {"message_id": msg.message_id}

    async def _handle_send_document(self, args: dict[str, Any]) -> dict[str, Any]:
        """``send_document {chat_id, host_path, caption?, filename?}`` → ``{message_id}``.

        ``host_path`` is an absolute path the broker can read. The broker
        currently shares the main app's filesystem and UID, so any path the
        agent emits via ``FileOutputPayload`` is reachable directly.
        """
        chat_id = _require_int(args, "chat_id")
        host_path = _require_str(args, "host_path")
        caption = args.get("caption")
        if caption is not None and not isinstance(caption, str):
            raise RpcError("BAD_REQUEST", "'caption' must be a string")
        filename = args.get("filename")
        if filename is not None and not isinstance(filename, str):
            raise RpcError("BAD_REQUEST", "'filename' must be a string")

        path = Path(host_path)
        if not path.is_file():
            raise RpcError("BAD_REQUEST", f"file not found: {host_path}")

        document = FSInputFile(str(path), filename=filename or path.name)
        try:
            msg = await self._bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=caption,
            )
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {"message_id": msg.message_id}

    async def _handle_send_chat_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """``send_chat_action {chat_id, action}`` → ``{}``.

        ``action`` is one of Telegram's chat-action values, e.g. ``"typing"``.
        The indicator clears after ~5 seconds — callers that want it to
        persist should re-send periodically.
        """
        chat_id = _require_int(args, "chat_id")
        action = _require_str(args, "action")
        try:
            await self._bot.send_chat_action(chat_id=chat_id, action=action)
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {}

    async def _handle_edit_message_text(self, args: dict[str, Any]) -> dict[str, Any]:
        """``edit_message_text {chat_id, message_id, text}`` → ``{}``.

        Edits a previously sent message in place. The channel uses this for a
        rolling status indicator that names the current activity rather than
        the generic "typing..." chat action.
        """
        chat_id = _require_int(args, "chat_id")
        message_id = _require_int(args, "message_id")
        text = _require_str(args, "text")
        try:
            await self._bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
            )
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {}

    async def _handle_delete_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """``delete_message {chat_id, message_id}`` → ``{}``.

        Removes a previously sent message. Used to clear the rolling status
        message once the turn ends so it doesn't clutter the chat history.
        """
        chat_id = _require_int(args, "chat_id")
        message_id = _require_int(args, "message_id")
        try:
            await self._bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {}

    async def _handle_answer_callback_query(self, args: dict[str, Any]) -> dict[str, Any]:
        """``answer_callback_query {callback_id, text?}`` → ``{}``.

        Acknowledges a callback_query so Telegram dismisses the button-tap
        loading spinner. Optional ``text`` shows a small toast to the user.
        """
        callback_id = _require_str(args, "callback_id")
        text = args.get("text")
        if text is not None and not isinstance(text, str):
            raise RpcError("BAD_REQUEST", "'text' must be a string")
        try:
            await self._bot.answer_callback_query(
                callback_query_id=callback_id,
                text=text,
            )
        except TelegramAPIError as exc:
            raise RpcError("INTERNAL", str(exc)) from exc
        return {}


def _coerce_inline_keyboard(buttons: Any) -> InlineKeyboardMarkup | None:
    """Turn a wire-format buttons grid into an aiogram InlineKeyboardMarkup.

    Wire format: ``[[{"text": "Label", "data": "payload"}, ...], ...]``.
    Returns ``None`` when ``buttons`` is missing or empty.
    """
    if buttons is None:
        return None
    if not isinstance(buttons, list):
        raise RpcError("BAD_REQUEST", "'buttons' must be a 2-D array of {text, data} dicts")
    rows: list[list[InlineKeyboardButton]] = []
    for row in buttons:
        if not isinstance(row, list):
            raise RpcError("BAD_REQUEST", "each 'buttons' row must be a list of dicts")
        button_row: list[InlineKeyboardButton] = []
        for cell in row:
            if not isinstance(cell, dict):
                raise RpcError("BAD_REQUEST", "each button must be a {text, data} dict")
            label = cell.get("text")
            data = cell.get("data")
            if not isinstance(label, str) or not label:
                raise RpcError("BAD_REQUEST", "button 'text' must be a non-empty string")
            if not isinstance(data, str) or not data:
                raise RpcError("BAD_REQUEST", "button 'data' must be a non-empty string")
            button_row.append(InlineKeyboardButton(text=label, callback_data=data))
        if button_row:
            rows.append(button_row)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value


def _require_int(args: dict[str, Any], key: str, *, default: int | None = None) -> int:
    if default is None:
        value = args.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RpcError("BAD_REQUEST", f"{key!r} required (integer)")
        return value
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RpcError("BAD_REQUEST", f"{key!r} must be an integer")
    return value
