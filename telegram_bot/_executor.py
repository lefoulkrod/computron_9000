"""Execute a single Telegram turn: receive message, run agent, send reply."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from agents.types import Data
from sdk.events import AgentEvent
from telegram_bot._formatter import TelegramFormatter
from telegram_bot._state import ConversationMap

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type alias for the handle_user_message callable.
# AsyncGenerator[AgentEvent, None] — same signature as server.message_handler.handle_user_message
HandleUserMessageFn = Callable[..., Coroutine[Any, Any, AsyncGenerator[AgentEvent, None]]]

__all__ = ["TelegramTurnExecutor"]


class TelegramTurnExecutor:
    """Bridges a single Telegram message into an agent turn.

    Usage::

        executor = TelegramTurnExecutor(bot=bot, state=state, handle_fn=handle_user_message)
        await executor.execute(chat_id, text)
    """

    def __init__(
        self,
        bot: Bot,
        state: ConversationMap,
        handle_fn: HandleUserMessageFn,
    ) -> None:
        self._bot = bot
        self._state = state
        self._handle_fn = handle_fn
        self._formatter = TelegramFormatter()

    # -- public API -----------------------------------------------------

    async def execute(
        self,
        chat_id: int,
        text: str,
        *,
        agent_id: str = "default",
        files: list[Data] | None = None,
        skills: list[str] | None = None,
    ) -> str | None:
        """Run one agent turn for the given *chat_id* and send the reply.

        Returns the final accumulated text, or None if the turn produced
        no text output.  The reply is sent to the chat as a side effect.
        """
        conversation_id = self._state.get(chat_id)
        logger.info(
            "telegram turn start  chat_id=%s  conversation_id=%s",
            chat_id,
            conversation_id,
        )

        collected_text = ""
        collected_files: list[Path] = []

        try:
            async for event in await self._handle_fn(
                conversation_id=conversation_id,
                user_message=text,
                agent_id=agent_id,
                files=files,
                skills=skills,
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
            await self._bot.send_message(
                chat_id,
                "⚠️ An error occurred while processing your message.",
            )
            return None

        # Send collected text
        if collected_text.strip():
            await self.send_text(chat_id, collected_text)

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
        return collected_text or None

    # -- sending helpers ------------------------------------------------

    async def send_text(self, chat_id: int, text: str) -> None:
        """Send *text* to *chat_id*, splitting if necessary."""
        chunks = self._formatter.split(text)
        for chunk in chunks:
            await self._bot.send_message(chat_id, chunk)

    async def _send_files(self, chat_id: int, paths: list[Path]) -> None:
        """Upload files as Telegram documents."""
        for i, path in enumerate(paths):
            if not path.exists():
                logger.warning("file not found, skipping: %s", path)
                continue
            caption = self._formatter.file_caption(path, index=i, total=len(paths))
            doc = FSInputFile(str(path), filename=path.name)
            await self._bot.send_document(
                chat_id,
                document=doc,
                caption=caption,
            )