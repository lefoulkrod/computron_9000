"""Telegram channel — polls for updates and dispatches agent turns."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from agents.types import LLMOptions
from conversations import load_conversation_history
from sdk.context import ConversationHistory
from sdk.turn import Conversation, TurnExecutor, is_turn_active, request_stop
from telegram._formatter import TelegramFormatter
from telegram._state import ConversationMap

if TYPE_CHECKING:
    from config import TelegramBotConfig

logger = logging.getLogger(__name__)

__all__ = ["TelegramChannel"]


class TelegramChannel:
    """Long-lived background service that polls Telegram for messages.

    Owns the conversation cache, turn executor, and send helpers.
    Lifecycle: ``start()`` / ``stop()``.
    """

    def __init__(self, config: TelegramBotConfig, default_model: str = "") -> None:
        self._config = config
        self._default_model = default_model
        self._state = ConversationMap()
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._poll_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._turn_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]
        self._router = Router()

        # Populated in start()
        self._turn_executor: TurnExecutor | None = None
        self._default_options: LLMOptions | None = None
        self._formatter = TelegramFormatter()
        self._conversations: dict[str, Conversation] = {}
        self._allowed_chat_ids: set[int] = set()

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

        # Build TurnExecutor and default LLM options
        self._turn_executor = TurnExecutor()
        model = self._config.model or self._default_model
        if not model:
            msg = "No model configured for Telegram. Set telegram.model in config or pass default_model."
            raise ValueError(msg)
        self._default_options = LLMOptions(model=model)
        self._allowed_chat_ids = allowed

        # Register handlers
        self._router.message.register(self._cmd_new, Command("new"))
        self._router.message.register(self._cmd_stop, Command("stop"))
        self._router.message.register(self._on_message)

        self._dispatcher = Dispatcher()
        self._dispatcher.include_router(self._router)

        self._poll_task = asyncio.create_task(
            self._dispatcher.start_polling(self._bot, allowed_updates=["message"]),
        )
        logger.info("telegram channel started  allowed_chats=%s", allowed)

    async def stop(self) -> None:
        """Stop polling and cancel in-flight turns."""
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
        logger.info("telegram channel stopped")

    # -- command handlers -----------------------------------------------

    async def _cmd_new(self, message: Message) -> None:
        """Handle /new — reset the conversation for this chat."""
        if not await self._check_allowed(message):
            return
        chat_id = message.chat.id
        conv_id = self._state.reset(chat_id)
        # Drop cached conversation so next message starts fresh
        self._conversations.pop(conv_id, None)
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
        """Execute a single agent turn and send the reply to Telegram."""
        conversation_id = self._state.get(chat_id)
        conversation, is_new = self._get_conversation(conversation_id)

        logger.info(
            "telegram turn start  chat_id=%s  conversation_id=%s  is_new=%s",
            chat_id,
            conversation_id,
            is_new,
        )

        collected_text = ""
        collected_files: list[Path] = []

        try:
            async for event in self._turn_executor.execute(  # type: ignore[union-attr]
                conversation=conversation,
                user_content=text,
                agent_id="default",
                options=self._default_options,  # type: ignore[arg-type]
                is_new_conversation=is_new,
            ):
                if event.type == "content":
                    payload = event.payload
                    if hasattr(payload, "text"):
                        collected_text += payload.text
                elif event.type == "file_output":
                    payload = event.payload
                    if hasattr(payload, "path"):
                        collected_files.append(Path(payload.path))

        except Exception:
            logger.exception(
                "telegram turn failed  chat_id=%s  conversation_id=%s",
                chat_id,
                conversation_id,
            )
            try:
                await self._bot.send_message(  # type: ignore[union-attr]
                    chat_id,
                    "⚠️ An error occurred while processing your message.",
                )
            except Exception:
                pass
            return

        # Send collected text
        if collected_text.strip():
            await self._send_text(chat_id, collected_text)

        # Send collected files
        if collected_files:
            await self._send_files(chat_id, collected_files)

        logger.info(
            "telegram turn end  chat_id=%s  conversation_id=%s  text_len=%d  files=%d",
            chat_id,
            conversation_id,
            len(collected_text),
            len(collected_files),
        )

    # -- conversation cache ---------------------------------------------

    def _get_conversation(self, conversation_id: str) -> tuple[Conversation, bool]:
        """Return the conversation for *conversation_id*, creating if needed.

        Returns:
            A tuple of (conversation, is_new) where *is_new* is True if the
            conversation was freshly created (not loaded from disk or cache).
        """
        if conversation_id in self._conversations:
            return self._conversations[conversation_id], False

        # Try to load persisted history from disk
        messages = load_conversation_history(conversation_id)
        if messages is not None:
            conversation = Conversation(
                id=conversation_id,
                history=ConversationHistory(messages, instance_id=conversation_id),
            )
            self._conversations[conversation_id] = conversation
            return conversation, False

        # Fresh conversation
        conversation = Conversation(
            id=conversation_id,
            history=ConversationHistory(instance_id=conversation_id),
        )
        self._conversations[conversation_id] = conversation
        return conversation, True

    # -- sending helpers ------------------------------------------------

    async def _send_text(self, chat_id: int, text: str) -> None:
        """Send *text* to *chat_id*, splitting if necessary."""
        chunks = self._formatter.split(text)
        for chunk in chunks:
            await self._bot.send_message(chat_id, chunk)  # type: ignore[union-attr]

    async def _send_files(self, chat_id: int, paths: list[Path]) -> None:
        """Upload files as Telegram documents."""
        for i, path in enumerate(paths):
            if not path.exists():
                logger.warning("file not found, skipping: %s", path)
                continue
            caption = self._formatter.file_caption(path, index=i, total=len(paths))
            doc = FSInputFile(str(path), filename=path.name)
            await self._bot.send_document(  # type: ignore[union-attr]
                chat_id,
                document=doc,
                caption=caption,
            )

    # -- access control -------------------------------------------------

    async def _check_allowed(self, message: Message) -> bool:
        """Return True if the message's chat is in the allowed list.

        If no allowed_chat_ids are configured, all chats are permitted.
        """
        if not self._allowed_chat_ids:
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