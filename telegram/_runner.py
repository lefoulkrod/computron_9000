"""Telegram channel — polls for updates and dispatches agent turns."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from agents import (
    AgentProfile,
    build_agent,
    get_agent_profile,
)
from agents.types import Agent
from conversations import (
    generate_conversation_title,
    load_conversation_history,
    load_loaded_skills,
    save_agent_events,
    save_conversation_title,
    save_loaded_skills,
)
from sdk import (
    PersistenceHook,
    default_hooks,
    run_turn,
)
from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events import (
    AgentEvent,
    agent_span,
    get_current_dispatcher,
)
from sdk.hooks._agent_event_buffer import AgentEventBufferHook
from sdk.skills import AgentState, get_skill
from sdk.tools._core import get_core_tools
from sdk.turn import is_turn_active, turn_scope
from sdk.turn._turn import StopRequestedError
from telegram._formatter import TelegramFormatter
from telegram._state import ConversationMap
from tools.memory import load_memory

if TYPE_CHECKING:
    from config import TelegramBotConfig

logger = logging.getLogger(__name__)

__all__ = ["TelegramChannel"]

# Track background tasks to avoid garbage collection (RUF006)
_background_tasks: set[asyncio.Task] = set()


def _refresh_system_message(history: ConversationHistory, system_prompt: str) -> None:
    """Re-insert the system message at the start of history with up-to-date memory."""
    instruction = system_prompt
    memory = load_memory()
    if memory:
        lines = "\n".join(f"  {k}: {e.value}" for k, e in memory.items())
        sep = "─" * 64
        memory_block = (
            f"\n── Memory (persisted across sessions) "
            f"──────────────────────────────────────────\n{lines}\n{sep}\n"
        )
        instruction = memory_block + instruction

    history.set_system_message(instruction)


def _build_agent_from_profile(profile: AgentProfile) -> Agent:
    """Construct an Agent from an AgentProfile."""
    from tools.memory import forget, remember
    from tools.virtual_computer.run_bash_cmd import run_bash_cmd

    return build_agent(profile, tools=[run_bash_cmd, remember, forget])


def _ensure_context_manager(
    conversation: _Conversation,
    active_agent: Agent,
) -> ContextManager:
    """Return the conversation's context manager, creating it if needed."""
    if conversation.context_manager is None:
        num_ctx = active_agent.options.get("num_ctx", 0) if active_agent.options else 0
        conversation.context_manager = ContextManager(
            history=conversation.history,
            context_limit=num_ctx,
            agent_name=active_agent.name,
            strategies=[ToolClearingStrategy(), LLMCompactionStrategy()],
        )
    return conversation.context_manager


async def _generate_title(conversation_id: str, first_message: str) -> None:
    """Generate and save a title for a new conversation."""
    try:
        title = await generate_conversation_title(first_message)
        save_conversation_title(conversation_id, title)
        logger.info("Generated title for conversation %s: %r", conversation_id, title)
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)


class _Conversation:
    """Per-conversation state: conversation history and context manager."""

    def __init__(self, history: ConversationHistory) -> None:
        self.history = history
        self.context_manager: ContextManager | None = None


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
        self._profile: AgentProfile | None = None
        self._active_agent: Agent | None = None
        self._formatter = TelegramFormatter()
        self._conversations: dict[str, _Conversation] = {}
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

        # Resolve the agent profile to use
        model = self._config.model or self._default_model
        if not model:
            msg = "No model configured for Telegram. Set telegram.model in config or pass default_model."
            raise ValueError(msg)

        # Use the computron default profile, overriding the model
        profile = get_agent_profile("computron")
        if profile is None:
            msg = "Default 'computron' profile not found"
            raise RuntimeError(msg)
        # Create a profile with the telegram-specific model
        self._profile = profile.model_copy(update={"model": model})
        self._active_agent = _build_agent_from_profile(self._profile)
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
            # Bridge published events via a queue
            queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

            async def _queue_handler(evt: AgentEvent) -> None:
                try:
                    await queue.put(evt)
                except Exception:
                    logger.exception("Failed to enqueue AgentEvent in TelegramChannel")

            async def _producer() -> None:
                try:
                    await self._execute_turn(
                        conversation=conversation,
                        user_content=text,
                        conversation_id=conversation_id,
                        handler=_queue_handler,
                        is_new_conversation=is_new,
                    )
                finally:
                    await queue.put(None)

            producer_task = asyncio.create_task(_producer())
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    # Collect content and file events
                    payload = item.payload
                    if item.type == "content" and hasattr(payload, "content"):
                        collected_text += payload.content
                    elif item.type == "file_output" and hasattr(payload, "path"):
                        collected_files.append(Path(payload.path))
            finally:
                if not producer_task.done():
                    producer_task.cancel()
                with suppress(Exception):
                    await producer_task

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

    async def _execute_turn(
        self,
        *,
        conversation: _Conversation,
        user_content: str,
        conversation_id: str,
        handler: Callable[[AgentEvent], object],
        is_new_conversation: bool = False,
    ) -> None:
        """Execute a single conversation turn: model calls, tool execution, persistence."""
        assert self._active_agent is not None
        assert self._profile is not None

        logger.info(
            "Turn started: conv=%s agent=%s message=%.80s",
            conversation_id,
            self._active_agent.name,
            user_content,
        )

        ctx_manager = _ensure_context_manager(conversation, self._active_agent)
        conv_id = conversation_id

        # Fresh AgentState each turn, restored from persisted skill names.
        # Pre-load skills from the profile.
        agent_state = AgentState(await get_core_tools() + self._active_agent.tools)
        for skill_name in self._profile.skills:
            skill = get_skill(skill_name)
            if skill is None:
                logger.warning("Profile skill '%s' not registered; skipping", skill_name)
                continue
            agent_state.add(skill)
            logger.info("Pre-loaded profile skill '%s' for conv=%s", skill_name, conv_id)
        for skill_name in load_loaded_skills(conv_id):
            if skill_name in agent_state.loaded_skill_names:
                continue
            skill = get_skill(skill_name)
            if skill is None:
                logger.warning(
                    "Persisted skill '%s' for conv=%s was not found in the skills registry; skipping",
                    skill_name,
                    conv_id,
                )
                continue
            agent_state.add(skill)
            logger.info("Restored skill '%s' for conv=%s", skill_name, conv_id)

        async with turn_scope(handler=handler, conversation_id=conversation_id):
            # Subscribe event buffer to capture agent lifecycle/preview events
            event_buffer = AgentEventBufferHook()
            dispatcher = get_current_dispatcher()
            if dispatcher:
                dispatcher.subscribe(event_buffer.handle_event)

            async with agent_span(
                self._active_agent.name,
                instruction=user_content,
                agent_state=agent_state,
                profile_name=self._profile.name,
            ):
                conversation.history.append({"role": "user", "content": user_content})
                # Build full system prompt: profile prompt + loaded skill prompts
                full_prompt = self._active_agent.instruction
                skill_prompt = agent_state.build_skill_prompt()
                if skill_prompt:
                    full_prompt = full_prompt + "\n" + skill_prompt
                _refresh_system_message(conversation.history, full_prompt)

                hooks = default_hooks(
                    self._active_agent,
                    max_iterations=self._active_agent.max_iterations,
                    ctx_manager=ctx_manager,
                )

                hooks.append(
                    PersistenceHook(
                        conversation_id=conv_id,
                        history=conversation.history,
                    )
                )

                with suppress(StopRequestedError):
                    await run_turn(
                        history=conversation.history,
                        agent=self._active_agent,
                        hooks=hooks,
                    )

            # Persist loaded skills so they survive across turns and restarts
            if agent_state.loaded_skill_names:
                try:
                    save_loaded_skills(conv_id, agent_state.loaded_skill_names)
                except Exception:
                    logger.exception("Failed to save loaded skills for '%s'", conv_id)

            # Yield to event loop so call_soon callbacks (sync event handlers)
            # have a chance to run before we read the buffer
            await asyncio.sleep(0)

            # Save agent events after the turn (outside agent_span so completion is captured)
            buffered_events = event_buffer.get_events()
            if buffered_events:
                try:
                    save_agent_events(conv_id, buffered_events)
                    logger.info("Saved %d agent events for conv=%s", len(buffered_events), conv_id)
                except Exception:
                    logger.exception("Failed to save agent events for '%s'", conv_id)

            # Generate a title for new conversations after the first successful turn
            if is_new_conversation and conversation_id:
                task = asyncio.create_task(_generate_title(conversation_id, user_content))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

    # -- conversation cache ---------------------------------------------

    def _get_conversation(self, conversation_id: str) -> tuple[_Conversation, bool]:
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
            conversation = _Conversation(
                history=ConversationHistory(messages, instance_id=conversation_id),
            )
            self._conversations[conversation_id] = conversation
            return conversation, False

        # Fresh conversation
        conversation = _Conversation(
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
