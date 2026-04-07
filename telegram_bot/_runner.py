"""Telegram bot runner: polls for updates and dispatches turns."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

from sdk.turn import is_turn_active, request_stop
from telegram_bot._executor import TelegramTurnExecutor
from telegram_bot._formatter import TelegramFormatter
from telegram_bot._state import ConversationMap

if TYPE_CHECKING:
    from config import TelegramBotConfig

logger = logging.getLogger(__name__)

__all__ = ["TelegramBotRunner"]


class TelegramBotRunner:
    """Long-lived background service that polls Telegram for messages.

    Mirrors the TaskRunner lifecycle pattern: ``start()`` / ``stop()``.
    """

    def __init__(self, config: TelegramBotConfig) -> None:
        self._config = config
        self._state = ConversationMap()
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._poll_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._turn_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]
        self._router = Router()

    # -- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        """Start polling for Telegram messages."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", self._config.token)
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set; Telegram bot not starting")
            return

        # Also read allowed chat IDs from env for convenience
        env_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        allowed = set(self._config.allowed_chat_ids)
        if env_chat_id:
            try:
                allowed.add(int(env_chat_id))
            except ValueError:
                logger.warning("TELEGRAM_CHAT_ID is not an integer: %s", env_chat_id)

        self._bot = Bot(token=token)
        self._executor = TelegramTurnExecutor(bot=self._bot, state=self._state)
        self._allowed_chat_ids = allowed

        # Register handlers
        self._router.message.register(self._cmd_new, Command("new"))
        self._router.message.register(self._cmd_stop, Command("stop"))
        self._router.message.register(self._on_message)

        self._dispatcher = Dispatcher()
        self._dispatcher.include_router(self._router)

        self._poll_task = asyncio.create_task(
            self._dispatcher.start_polling(self._bot, allowed_updates=Message),
        )
        logger.info("telegram bot started  allowed_chats=%s", allowed)

    async def stop(self) -> None:
        """Stop polling and cancel in-flight turns."""
        if self._dispatcher:
            await self._dispatcher.stop_polling()
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        # Cancel any still-running turn tasks
        for task in self._turn_tasks:
            task.cancel()
        if self._turn_tasks:
            await asyncio.gather(*self._turn_tasks, return_exceptions=True)
        if self._bot:
            await self._bot.session.close()
        logger.info("telegram bot stopped")

    # -- command handlers -----------------------------------------------

    async def _cmd_new(self, message: Message) -> None:
        """Handle /new — reset the conversation for this chat."""
        if not await self._check_allowed(message):
            return
        chat_id = message.chat.id
        conv_id = self._state.reset(chat_id)
        await message.reply(f"🔄 New conversation started (`{conv_id}`)")
        logger.info("telegram /new  chat_id=%s  conv_id=%s", chat_id, conv_id)

    async def _cmd_stop(self, message: Message) -> None:
        """Handle /stop — request the current turn to stop."""
        if not await self._check_allowed(message):
            return
        chat_id = message.chat.id
        conv_id = self._state.conversation_id_for(chat_id)
        if conv_id and is_turn_active(conv_id):
            request_stop(conv_id)
            await message.reply("⏹ Stop requested")
            logger.info("telegram /stop  chat_id=%s  conv_id=%s", chat_id, conv_id)
        else:
            await message.reply("No active turn to stop")

    # -- message handler ------------------------------------------------

    async def _on_message(self, message: Message) -> None:
        """Handle a regular text message by spawning a turn task."""
        if not await self._check_allowed(message):
            return
        if not message.text:
            return

        chat_id = message.chat.id
        text = message.text

        # Check if a turn is already active for this conversation
        conv_id = self._state.get(chat_id)
        if is_turn_active(conv_id):
            await message.reply("⏳ A turn is already running. Use /stop to cancel it.")
            return

        # Launch as a background task
        task = asyncio.create_task(self._run_turn(chat_id, text))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)

    async def _run_turn(self, chat_id: int, text: str) -> None:
        """Execute a single turn (runs as a background task)."""
        try:
            await self._executor.execute(chat_id, text)
        except Exception:
            logger.exception("telegram turn task failed  chat_id=%s", chat_id)
            try:
                await self._bot.send_message(  # type: ignore[union-attr]
                    chat_id,
                    "⚠️ An unexpected error occurred.",
                )
            except Exception:
                pass

    # -- access control -------------------------------------------------

    async def _check_allowed(self, message: Message) -> bool:
        """Return True if the message's chat is in the allowed list.

        If no allowed_chat_ids are configured, all chats are permitted.
        """
        if not hasattr(self, "_allowed_chat_ids"):
            return True
        if not self._allowed_chat_ids:
            # Empty allow-list means allow all
            return True
        if message.chat.id in self._allowed_chat_ids:
            return True
        await message.reply("⛔ Unauthorized")
        logger.warning(
            "telegram unauthorized chat_id=%s  user=%s",
            message.chat.id,
            message.from_user,
        )
        return False