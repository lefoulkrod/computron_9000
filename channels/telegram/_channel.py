"""Telegram channel — talks to the telegram broker over RPC.

The channel no longer holds the bot token or the aiogram client. It pulls
incoming messages from the broker via the ``next_updates`` long-poll verb
and sends outbound text via ``send_message``. All sender allowlist
enforcement lives in the broker; this process trusts whatever the broker
forwards.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from agents import build_agent, get_agent_profile, list_agent_profiles
from agents.types import Agent
from channels.telegram._formatter import TelegramFormatter
from channels.telegram._profile_map import ProfileMap
from channels.telegram._state import ConversationMap
from conversations import (
    ConversationCache,
    DiskTurnPersistence,
    list_conversations,
    load_conversation_history,
)
from conversations._models import ConversationSummary
from integrations import supervisor_client
from integrations.broker_client import (
    IntegrationAuthFailed,
    IntegrationError,
    IntegrationNotConnected,
    call as broker_call,
)
from sdk import TurnExecutor
from sdk.events import AgentEvent
from sdk.skills import AgentState
from sdk.turn import is_turn_active, request_stop
from tools.memory import forget, memory_prompt_block, remember
from tools.virtual_computer.run_bash_cmd import run_bash_cmd

logger = logging.getLogger(__name__)

__all__ = ["TelegramChannel"]

# Long-poll window the channel asks the broker to hold each call for.
_LONG_POLL_TIMEOUT_MS = 30_000

# Exponential backoff bounds for transient broker errors.
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 30.0

# Backoff used when the broker reports a state the user has to fix
# (auth_failed, not_connected). Polling fast doesn't help — wait longer.
_LONG_BACKOFF_SECONDS = 60.0

# Telegram's chat-action indicator clears after ~5 seconds. Re-send every 4
# so the "typing…" header stays visible across a multi-minute turn.
_TYPING_INDICATOR_INTERVAL_SECONDS = 4.0

# callback_data prefix encoding profile picks. Keeps the payload format
# self-describing so unrelated callbacks (future verbs) don't collide.
_PROFILE_CALLBACK_PREFIX = "profile:"

# callback_data prefix for picking a past conversation to resume.
_CONV_CALLBACK_PREFIX = "conv:"

# How many past conversations to show in a /list reply. Keeps the inline
# keyboard within Telegram's reasonable-rendering range and the chat tidy.
_LIST_MAX_RESULTS = 10

# Initial status text shown while we wait for the first event from the agent.
_STATUS_THINKING = "🤔 Thinking..."
_STATUS_WRITING = "✍️ Writing response..."


class TelegramChannel:
    """Pulls updates from the telegram broker and dispatches agent turns."""

    def __init__(self, *, app_sock_path: Path) -> None:
        self._app_sock = app_sock_path
        self._state = ConversationMap()
        self._profiles = ProfileMap()
        self._formatter = TelegramFormatter()
        self._turn_executor = TurnExecutor()
        self._persistence = DiskTurnPersistence()
        # Same bounded LRU the web/SSE side uses; on_evict is None because
        # the channel doesn't own per-conversation Playwright contexts.
        self._cache = ConversationCache(is_active=is_turn_active)
        self._integration_id: str = ""
        self._default_profile_id: str = "computron"
        self._pull_task: asyncio.Task[None] | None = None
        self._turn_tasks: set[asyncio.Task[None]] = set()
        # Fire-and-forget tasks (e.g. title generation on first turn). Held
        # so the GC doesn't reap them; cleared via done_callback.
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Per-chat in-flight turn tracker. Owned by the dispatch loop so the
        # "one turn at a time" check is race-free — ContextVar-based
        # ``is_turn_active`` doesn't flip True until the task actually runs,
        # so two messages in the same broker batch would both pass that
        # check and double-spawn.
        self._turn_by_chat: dict[int, asyncio.Task[None]] = {}
        self._stopping = False
        # Signalled by ``notify_integration_added`` so the supervise loop
        # wakes the moment the user finishes the wizard. Default-low; the
        # supervise loop clears it before each retry.
        self._integration_added_event = asyncio.Event()

    def notify_integration_added(self, slug: str) -> None:
        """Wake the supervise loop after a relevant integration is added.

        The integrations HTTP route calls this on every successful add.
        Filters by slug so adding Gmail or iCloud doesn't trigger any
        Telegram-side work.
        """
        if slug == "telegram":
            self._integration_added_event.set()

    # -- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        """Launch the supervisor task; discovery happens lazily.

        Channels boot once at app start, but integrations can be added at any
        time via the wizard. So discovery runs inside a background task that
        polls until a Telegram integration appears, then transitions into the
        pull loop. ``start()`` itself returns immediately.
        """
        self._pull_task = asyncio.create_task(
            self._supervise(), name="telegram-supervise",
        )

    async def _supervise(self) -> None:
        """Wait for a Telegram integration to exist, probe it, then pull."""
        integration_id = await self._wait_for_integration()
        if integration_id is None:
            # Stopping was requested before discovery succeeded.
            return
        self._integration_id = integration_id

        try:
            me = await broker_call(
                integration_id, "get_me", {}, app_sock_path=self._app_sock,
            )
        except IntegrationNotConnected:
            logger.warning(
                "Telegram integration %r vanished between discovery and probe; "
                "channel not starting",
                integration_id,
            )
            return
        except IntegrationAuthFailed as exc:
            logger.error(
                "Telegram integration %r auth failed; channel not starting: %s",
                integration_id, exc,
            )
            return
        except IntegrationError as exc:
            logger.error(
                "Telegram broker probe failed for %r; channel not starting: %s",
                integration_id, exc,
            )
            return

        logger.info(
            "telegram channel started  integration_id=%s  bot=@%s (id=%d)",
            integration_id, me.get("username"), me.get("id"),
        )
        await self._pull_loop()

    async def _wait_for_integration(self) -> str | None:
        """Discover or wait for a Telegram integration.

        No polling: discovery runs once. If nothing's registered, the
        supervise task parks on an event that the integrations HTTP route
        sets when a Telegram integration is added. Returns the integration
        id, or ``None`` if the channel was stopped while waiting.
        """
        while not self._stopping:
            integration_id = await self._discover_integration()
            if integration_id is not None:
                return integration_id
            logger.info(
                "No Telegram integration registered; channel waiting for one "
                "to be added via the wizard",
            )
            self._integration_added_event.clear()
            await self._integration_added_event.wait()
        return None

    async def _discover_integration(self) -> str | None:
        """Pick the telegram integration the channel should bind to.

        Returns the integration_id, or None if no telegram integration is
        registered. With multiple registered, the first is chosen and the
        choice is logged.
        """
        try:
            result = await supervisor_client.call(
                "list", {}, app_sock_path=self._app_sock,
            )
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            logger.warning(
                "Supervisor unreachable; Telegram channel not starting: %s", exc,
            )
            return None

        telegrams = [
            i for i in result.get("integrations", [])
            if i.get("slug") == "telegram"
        ]
        if not telegrams:
            return None
        if len(telegrams) > 1:
            ids = sorted(i["id"] for i in telegrams)
            logger.warning(
                "Multiple Telegram integrations registered (%s); binding to %s. "
                "Multi-integration support is a future feature.",
                ids, telegrams[0]["id"],
            )
        return telegrams[0]["id"]

    async def stop(self) -> None:
        """Stop the pull loop and any in-flight turns."""
        self._stopping = True
        # Wake the supervise loop if it's parked waiting for an integration —
        # cancel alone is enough, but setting the event keeps the code path
        # symmetric with the add-side wake.
        self._integration_added_event.set()
        if self._pull_task is not None:
            self._pull_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pull_task
        for task in list(self._turn_tasks):
            task.cancel()
        if self._turn_tasks:
            await asyncio.gather(*self._turn_tasks, return_exceptions=True)
        logger.info("telegram channel stopped")

    # -- pull loop ------------------------------------------------------

    async def _pull_loop(self) -> None:
        """Long-poll the broker for incoming messages and dispatch each."""
        backoff = _BACKOFF_INITIAL_SECONDS
        while not self._stopping:
            try:
                result = await broker_call(
                    self._integration_id,
                    "next_updates",
                    {"timeout_ms": _LONG_POLL_TIMEOUT_MS},
                    app_sock_path=self._app_sock,
                )
                backoff = _BACKOFF_INITIAL_SECONDS
            except asyncio.CancelledError:
                raise
            except IntegrationAuthFailed as exc:
                logger.error(
                    "telegram broker auth failed (will retry in %.0fs): %s",
                    _LONG_BACKOFF_SECONDS, exc,
                )
                await asyncio.sleep(_LONG_BACKOFF_SECONDS)
                continue
            except IntegrationNotConnected as exc:
                logger.warning(
                    "telegram broker not connected (will retry in %.0fs): %s",
                    _LONG_BACKOFF_SECONDS, exc,
                )
                await asyncio.sleep(_LONG_BACKOFF_SECONDS)
                continue
            except IntegrationError as exc:
                logger.warning(
                    "telegram broker call failed (retrying in %.1fs): %s",
                    backoff, exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP_SECONDS)
                continue
            except Exception:
                # Defensive: anything else is a bug, but a crashed pull task
                # silently stops the bot until app restart. Log with traceback
                # and back off rather than die.
                logger.exception(
                    "telegram pull loop: unexpected error (retrying in %.1fs)",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP_SECONDS)
                continue

            for update in result.get("updates", []):
                await self._dispatch(update)

    # -- dispatch -------------------------------------------------------

    async def _dispatch(self, update: dict[str, Any]) -> None:
        """Route a single update to the right handler."""
        kind = update.get("type")
        if kind == "message":
            await self._dispatch_message(update)
        elif kind == "callback_query":
            await self._dispatch_callback(update)

    async def _dispatch_message(self, update: dict[str, Any]) -> None:
        chat_id = update["chat_id"]
        text = update.get("text")
        attachments = update.get("attachments") or []

        if update.get("is_command"):
            parts = text.split(maxsplit=1)
            cmd = parts[0][1:]  # strip leading "/"
            arg = parts[1] if len(parts) > 1 else ""
            if cmd == "new":
                await self._handle_new(chat_id)
            elif cmd == "stop":
                await self._handle_stop(chat_id)
            elif cmd == "profile":
                await self._handle_profile(chat_id)
            elif cmd == "list":
                await self._handle_list(chat_id, arg)
            elif cmd == "help":
                await self._handle_help(chat_id)
            else:
                await self._send_text(chat_id, f"Unknown command: /{cmd}")
            return

        # Text only, attachments only, or both — all flow through one turn.
        # Build the augmented user_content here so the agent sees a single
        # human-readable description rather than a flag dict.
        user_content = _build_user_content(text, attachments)
        if not user_content:
            # Nothing actionable (would be unusual — broker already filters
            # bare messages with neither text nor attachments).
            return

        existing = self._turn_by_chat.get(chat_id)
        if existing is not None and not existing.done():
            await self._send_text(
                chat_id, "⏳ A turn is already running. Use /stop to cancel it.",
            )
            return

        task = asyncio.create_task(self._run_turn(chat_id, user_content))
        self._turn_tasks.add(task)
        self._turn_by_chat[chat_id] = task

        def _on_done(t: asyncio.Task[None]) -> None:
            self._turn_tasks.discard(t)
            # Only clear if this is still the current one — a /stop + new
            # message could have already swapped a fresh task in.
            if self._turn_by_chat.get(chat_id) is t:
                self._turn_by_chat.pop(chat_id, None)

        task.add_done_callback(_on_done)

    async def _dispatch_callback(self, update: dict[str, Any]) -> None:
        """Handle an inline-keyboard button tap."""
        callback_id = update["callback_id"]
        chat_id = update["chat_id"]
        data = update["data"]

        if data.startswith(_PROFILE_CALLBACK_PREFIX):
            profile_id = data[len(_PROFILE_CALLBACK_PREFIX):]
            await self._select_profile(chat_id, profile_id, callback_id)
            return

        if data.startswith(_CONV_CALLBACK_PREFIX):
            target = data[len(_CONV_CALLBACK_PREFIX):]
            await self._resume_conversation(chat_id, target, callback_id)
            return

        # Unknown callback — dismiss the loading spinner anyway so the
        # Telegram client doesn't sit on it forever.
        await self._answer_callback(callback_id)

    # -- command handlers -----------------------------------------------

    async def _handle_new(self, chat_id: int) -> None:
        conv_id = self._state.reset(chat_id)
        self._cache.pop(conv_id)
        await self._send_text(chat_id, f"🔄 New conversation started ({conv_id})")
        logger.info("telegram /new  chat_id=%s  conv_id=%s", chat_id, conv_id)

    async def _handle_stop(self, chat_id: int) -> None:
        conv_id = self._state.conversation_id_for(chat_id)
        if conv_id and is_turn_active(conv_id):
            request_stop(conv_id)
            await self._send_text(chat_id, "⏹ Stop requested")
            logger.info("telegram /stop  chat_id=%s  conv_id=%s", chat_id, conv_id)
        else:
            await self._send_text(chat_id, "No active turn to stop")

    async def _handle_profile(self, chat_id: int) -> None:
        """Show the profile picker as an inline keyboard."""
        profiles = list_agent_profiles()
        if not profiles:
            await self._send_text(chat_id, "No agent profiles available.")
            return

        current = self._profiles.get(chat_id) or self._default_profile_id
        # One button per row keeps long profile lists readable on mobile.
        buttons = [
            [{
                "text": f"{'✓ ' if p.id == current else ''}{p.name}",
                "data": f"{_PROFILE_CALLBACK_PREFIX}{p.id}",
            }]
            for p in profiles
        ]
        try:
            await broker_call(
                self._integration_id,
                "send_message",
                {
                    "chat_id": chat_id,
                    "text": "Pick an agent profile for this chat:",
                    "buttons": buttons,
                },
                app_sock_path=self._app_sock,
            )
        except IntegrationError as exc:
            logger.warning("telegram /profile failed chat_id=%s: %s", chat_id, exc)

    async def _handle_help(self, chat_id: int) -> None:
        lines = [
            "Commands:",
            "  /new          — start a new conversation",
            "  /stop         — stop the current turn",
            "  /profile      — pick an agent profile for this chat",
            "  /list [query] — list past conversations, optionally filtered",
            "  /help         — this message",
        ]
        await self._send_text(chat_id, "\n".join(lines))

    async def _handle_list(self, chat_id: int, query: str) -> None:
        """Show past conversations as an inline keyboard.

        Lists every conversation in the store (Telegram, web, anywhere) —
        the conversation store is the single source of truth and the user
        shouldn't have to remember where they started. Optional ``query``
        is a case-insensitive substring match on title and first message.
        """
        query = query.strip()
        summaries = list_conversations()
        matches = [
            s for s in summaries
            if not query or _matches_query(s, query)
        ][:_LIST_MAX_RESULTS]

        if not matches:
            msg = (
                f"No conversations match '{query}'."
                if query
                else "No past conversations yet."
            )
            await self._send_text(chat_id, msg)
            return

        current = self._state.conversation_id_for(chat_id)
        buttons = [
            [{
                "text": _row_label(s, is_current=s.conversation_id == current),
                "data": f"{_CONV_CALLBACK_PREFIX}{s.conversation_id}",
            }]
            for s in matches
        ]
        header = (
            f"Conversations matching '{query}':"
            if query
            else "Recent conversations:"
        )
        try:
            await broker_call(
                self._integration_id,
                "send_message",
                {"chat_id": chat_id, "text": header, "buttons": buttons},
                app_sock_path=self._app_sock,
            )
        except IntegrationError as exc:
            logger.warning("telegram /list failed chat_id=%s: %s", chat_id, exc)

    async def _resume_conversation(
        self, chat_id: int, conv_id: str, callback_id: str,
    ) -> None:
        """Bind this chat to *conv_id* so the next message continues it.

        Callback data is whatever the bot put on the button — only valid
        conversation ids are sent — so no per-chat prefix validation is
        needed here. The disk check below catches a stale callback whose
        conversation was deleted between list-and-tap.
        """
        if load_conversation_history(conv_id) is None:
            await self._answer_callback(callback_id, text="Conversation not found")
            return

        self._state.set(chat_id, conv_id)
        # Drop the cached in-memory Conversation so the next turn rehydrates
        # the picked one's history from disk.
        self._cache.pop(conv_id)
        await self._answer_callback(callback_id, text="Resumed")
        await self._send_text(chat_id, f"📂 Resumed conversation: {conv_id}")
        logger.info(
            "telegram resumed conversation  chat_id=%s  conv_id=%s",
            chat_id, conv_id,
        )

    async def _select_profile(
        self, chat_id: int, profile_id: str, callback_id: str,
    ) -> None:
        """Record the user's profile choice and acknowledge."""
        profile = get_agent_profile(profile_id)
        if profile is None or not profile.enabled:
            await self._answer_callback(callback_id, text="Profile unavailable")
            return
        self._profiles.set(chat_id, profile_id)
        # Tiny toast on the button tap + a normal reply for the chat history.
        await self._answer_callback(callback_id, text=f"Profile: {profile.name}")
        await self._send_text(chat_id, f"✅ Profile set to {profile.name}")
        logger.info(
            "telegram profile selected  chat_id=%s  profile_id=%s",
            chat_id, profile_id,
        )

    # -- turn execution -------------------------------------------------

    async def _run_turn(self, chat_id: int, text: str) -> None:
        """Execute one agent turn for the given chat and deliver the reply."""
        conversation_id = self._state.get(chat_id)
        conversation, is_new = await self._cache.get(conversation_id)

        profile = self._resolve_profile(chat_id)
        if profile is None:
            await self._send_text(
                chat_id, "⚠️ No agent profile available. Set one with /profile.",
            )
            return

        if conversation.agent_state is None:
            conversation.agent_state = await AgentState.create(
                skill_names=[
                    *profile.skills,
                    *self._persistence.load_skills(conversation.id),
                ],
            )

        agent = build_agent(profile, tools=[run_bash_cmd, remember, forget])
        agent.instruction = memory_prompt_block() + agent.instruction

        logger.info(
            "telegram turn start  chat_id=%s  conversation_id=%s  is_new=%s  profile=%s",
            chat_id, conversation_id, is_new, profile.id,
        )

        typing_task = asyncio.create_task(
            self._keep_typing(chat_id), name="telegram-typing",
        )
        status = _StatusMessage(chat_id, self)
        await status.start(_STATUS_THINKING)
        collected_text = ""
        file_paths: list[str] = []
        wrote_started = False
        events: list[AgentEvent] = []

        try:
            async for event in self._turn_executor.execute(
                conversation=conversation,
                agent=agent,
                user_content=text,
                profile_name=profile.name,
            ):
                events.append(event)
                payload = event.payload
                ptype = payload.type
                if ptype == "tool_call" and hasattr(payload, "name"):
                    await status.set(f"🔧 Calling {payload.name}...")
                elif ptype == "agent_started" and hasattr(payload, "agent_name"):
                    await status.set(f"🚀 Spawning {payload.agent_name}...")
                elif ptype == "agent_completed":
                    await status.set(_STATUS_THINKING)
                elif ptype == "content" and hasattr(payload, "content"):
                    if payload.content:
                        collected_text += payload.content
                        if not wrote_started:
                            wrote_started = True
                            await status.set(_STATUS_WRITING)
                elif ptype == "file_output" and hasattr(payload, "path"):
                    if payload.path:
                        file_paths.append(payload.path)
        except Exception:
            logger.exception(
                "telegram turn failed  chat_id=%s  conversation_id=%s",
                chat_id, conversation_id,
            )
            await status.clear()
            await self._send_text(
                chat_id, "⚠️ An error occurred while processing your message.",
            )
            return
        finally:
            typing_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await typing_task

        await status.clear()

        if collected_text.strip():
            await self._send_text(chat_id, collected_text)

        for path in file_paths:
            await self._send_document(chat_id, path)

        # Post-turn persistence. Errors logged, never raised — the user
        # already got their reply.
        try:
            self._persistence.save_events(conversation.id, events)
        except Exception:
            logger.exception(
                "Failed to save agent events for '%s'", conversation.id,
            )
        if conversation.agent_state.loaded_skill_names:
            try:
                self._persistence.save_skills(
                    conversation.id,
                    conversation.agent_state.loaded_skill_names,
                )
            except Exception:
                logger.exception(
                    "Failed to save loaded skills for '%s'", conversation.id,
                )
        if is_new:
            task = asyncio.create_task(
                self._persistence.on_new_conversation(conversation.id, text),
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        logger.info(
            "telegram turn end  chat_id=%s  conversation_id=%s  text_len=%d  files=%d",
            chat_id, conversation_id, len(collected_text), len(file_paths),
        )

    def _resolve_profile(self, chat_id: int):
        """Return the AgentProfile for *chat_id* — picked, default, or None.

        The profile's own ``model`` field is the source of truth. There's no
        Telegram-specific model override anymore; pick a different profile
        via ``/profile`` if you want a different model on Telegram.
        """
        for candidate in (self._profiles.get(chat_id), self._default_profile_id):
            if not candidate:
                continue
            profile = get_agent_profile(candidate)
            if profile is None or not profile.enabled:
                continue
            return profile
        return None

    async def _keep_typing(self, chat_id: int) -> None:
        """Re-send the typing indicator on a loop while a turn is running.

        Telegram's chat-action lasts ~5 seconds; loop slightly faster so
        the indicator never gaps. Stops when the task is cancelled.
        """
        try:
            while True:
                try:
                    await broker_call(
                        self._integration_id,
                        "send_chat_action",
                        {"chat_id": chat_id, "action": "typing"},
                        app_sock_path=self._app_sock,
                    )
                except IntegrationError as exc:
                    # Transient broker hiccup — drop this beat and try again.
                    logger.debug(
                        "telegram send_chat_action failed (will retry): %s", exc,
                    )
                await asyncio.sleep(_TYPING_INDICATOR_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise

    # -- outbound -------------------------------------------------------

    async def _send_text(self, chat_id: int, text: str) -> None:
        """Send *text* to *chat_id*, splitting if necessary.

        Agent output is CommonMark-flavored markdown. We convert to
        Telegram MarkdownV2 and tag the send with ``parse_mode`` so the
        formatting renders natively instead of showing as literal
        asterisks and backticks.
        """
        for chunk in self._formatter.to_markdownv2_chunks(text):
            try:
                await broker_call(
                    self._integration_id,
                    "send_message",
                    {
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "MarkdownV2",
                    },
                    app_sock_path=self._app_sock,
                )
            except IntegrationError as exc:
                logger.warning(
                    "telegram send_message failed  chat_id=%s: %s", chat_id, exc,
                )
                return

    async def _send_document(self, chat_id: int, host_path: str) -> None:
        """Upload *host_path* as a Telegram document.

        Reads the file via the broker so the channel never touches the bot
        token. Errors are logged and the upload is skipped — the rest of
        the reply still goes through.
        """
        path = Path(host_path)
        caption = self._formatter.file_caption(path)
        try:
            await broker_call(
                self._integration_id,
                "send_document",
                {
                    "chat_id": chat_id,
                    "host_path": str(host_path),
                    "caption": caption,
                    "filename": path.name,
                },
                app_sock_path=self._app_sock,
            )
        except IntegrationError as exc:
            logger.warning(
                "telegram send_document failed  chat_id=%s  path=%s: %s",
                chat_id, host_path, exc,
            )

    async def _answer_callback(
        self, callback_id: str, *, text: str | None = None,
    ) -> None:
        """Dismiss the loading spinner on an inline-keyboard button tap."""
        args: dict[str, Any] = {"callback_id": callback_id}
        if text is not None:
            args["text"] = text
        try:
            await broker_call(
                self._integration_id,
                "answer_callback_query",
                args,
                app_sock_path=self._app_sock,
            )
        except IntegrationError as exc:
            logger.debug("telegram answer_callback_query failed: %s", exc)


def _matches_query(summary: ConversationSummary, query: str) -> bool:
    """Case-insensitive substring match on title and first message."""
    needle = query.lower()
    return (
        needle in (summary.title or "").lower()
        or needle in (summary.first_message or "").lower()
    )


def _row_label(summary: ConversationSummary, *, is_current: bool) -> str:
    """Human-readable label for a /list inline-keyboard row."""
    if summary.title:
        body = summary.title
    elif summary.first_message:
        # Some conversations don't get a title (turn errored before
        # title-generation fired). Fall back to a clipped first message.
        body = f"({summary.first_message[:50]}…)"
    else:
        body = f"(empty • {summary.conversation_id})"
    # Telegram button labels render best within ~64 chars.
    body = body[:60]
    prefix = "✓ " if is_current else ""
    return f"{prefix}{body}"


def _build_user_content(
    text: str | None, attachments: list[dict[str, Any]],
) -> str:
    """Compose the agent-facing user message from text + attachment paths.

    Mirrors the SSE channel's ``_augment_message_with_attachments`` shape so
    the agent sees consistent file references regardless of how the message
    arrived (web upload vs. Telegram document).
    """
    body = (text or "").strip()
    if not attachments:
        return body
    lines: list[str] = []
    for att in attachments:
        path = att.get("path")
        if not path:
            continue
        name = att.get("file_name") or path.rsplit("/", 1)[-1]
        mime = att.get("mime_type") or "application/octet-stream"
        lines.append(f"  - {name} ({mime}) -> {path}")
    if not lines:
        return body
    files_block = "\n".join(lines)
    if body:
        return f"{body}\n\n[Attached files written to virtual computer]\n{files_block}"
    return f"[Attached files written to virtual computer]\n{files_block}"


class _StatusMessage:
    """A live status message that the channel edits in place during a turn.

    Sends one Telegram message at turn start (capturing its message_id),
    edits the text on state transitions (tool calls, sub-agent spawns,
    response writing), and deletes the message before the final reply.
    Falls back to silent no-ops if the initial send or any edit fails so
    a broker hiccup never breaks the turn itself.
    """

    def __init__(self, chat_id: int, channel: TelegramChannel) -> None:
        self._chat_id = chat_id
        self._channel = channel
        self._message_id: int | None = None
        self._current: str | None = None

    async def start(self, text: str) -> None:
        """Post the initial status message and capture its message_id."""
        try:
            result = await broker_call(
                self._channel._integration_id,
                "send_message",
                {"chat_id": self._chat_id, "text": text},
                app_sock_path=self._channel._app_sock,
            )
            self._message_id = result.get("message_id")
            self._current = text
        except IntegrationError as exc:
            logger.debug("telegram status send_message failed: %s", exc)

    async def set(self, text: str) -> None:
        """Edit the status to *text* if it differs from the current value."""
        if self._message_id is None or text == self._current:
            return
        try:
            await broker_call(
                self._channel._integration_id,
                "edit_message_text",
                {
                    "chat_id": self._chat_id,
                    "message_id": self._message_id,
                    "text": text,
                },
                app_sock_path=self._channel._app_sock,
            )
            self._current = text
        except IntegrationError as exc:
            logger.debug("telegram status edit_message_text failed: %s", exc)

    async def clear(self) -> None:
        """Delete the status message. Safe to call multiple times."""
        if self._message_id is None:
            return
        message_id = self._message_id
        self._message_id = None
        try:
            await broker_call(
                self._channel._integration_id,
                "delete_message",
                {"chat_id": self._chat_id, "message_id": message_id},
                app_sock_path=self._channel._app_sock,
            )
        except IntegrationError as exc:
            logger.debug("telegram status delete_message failed: %s", exc)
