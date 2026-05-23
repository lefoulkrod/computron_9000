"""Long-polling update pump.

Pulls updates from Telegram in the background and pushes allowed ones onto
an internal queue. Verb handlers drain the queue via ``next_updates``.

Drops from non-allowlisted senders are silent — replying would confirm the
bot is live and waste outbound rate limits. Drop counts are logged
periodically rather than per-message so a spam burst doesn't spam the log.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError

logger = logging.getLogger(__name__)

__all__ = ["UpdatePump", "update_to_dict"]

# How often to surface aggregate drop counts. A spam burst at this interval
# produces at most one log line per chat ID per window.
_DROP_LOG_INTERVAL_SECONDS = 60.0

# Long-poll timeout in seconds — how long Telegram holds the request open
# waiting for an update before returning an empty list. 25 is comfortably
# under typical proxy/load-balancer timeouts and matches aiogram's default.
_LONG_POLL_TIMEOUT_SECONDS = 25

# Backoff for transient network errors. The first failure waits 1s; each
# subsequent failure doubles up to the cap. Resets on the first success.
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 30.0


def update_to_dict(update: Any) -> dict[str, Any] | None:
    """Flatten an aiogram ``Update`` to the wire shape, or ``None`` to skip.

    Forwards text ``message`` updates and ``callback_query`` updates
    (inline-keyboard button taps). Other update kinds are dropped.
    """
    message = getattr(update, "message", None)
    if message is not None:
        return _message_to_dict(message)
    callback = getattr(update, "callback_query", None)
    if callback is not None:
        return _callback_to_dict(callback)
    return None


def _message_to_dict(message: Any) -> dict[str, Any] | None:
    text = getattr(message, "text", None)
    if not text:
        return None
    user = message.from_user
    if user is None:
        return None
    return {
        "type": "message",
        "message_id": message.message_id,
        "chat_id": message.chat.id,
        "from_user_id": user.id,
        "from_username": getattr(user, "username", None),
        "text": text,
        "is_command": text.startswith("/"),
        "timestamp": int(message.date.timestamp()) if message.date else int(time.time()),
    }


def _callback_to_dict(callback: Any) -> dict[str, Any] | None:
    """Flatten a callback_query (inline-keyboard button tap) to the wire shape."""
    user = getattr(callback, "from_user", None)
    if user is None:
        return None
    data = getattr(callback, "data", None)
    if data is None:
        return None
    msg = getattr(callback, "message", None)
    chat_id = msg.chat.id if (msg is not None and msg.chat is not None) else None
    message_id = msg.message_id if msg is not None else None
    if chat_id is None or message_id is None:
        return None
    return {
        "type": "callback_query",
        "callback_id": callback.id,
        "from_user_id": user.id,
        "from_username": getattr(user, "username", None),
        "data": data,
        "chat_id": chat_id,
        "message_id": message_id,
        "timestamp": int(time.time()),
    }


class UpdatePump:
    """Background long-poller. Allowed updates land on ``self.queue``."""

    def __init__(
        self,
        bot: Bot,
        allowed_user_ids: frozenset[int],
        *,
        integration_id: str,
    ) -> None:
        self._bot = bot
        self._allowed = allowed_user_ids
        self._integration_id = integration_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # Aggregate drop tracking — keyed by sender so a single bad actor
        # contributes one log line per window even if they send thousands.
        self._drop_counts: dict[int, int] = {}
        self._drop_window_started_at: float = time.monotonic()

        # Set to True only after the pump observes an Unauthorized response,
        # so __main__ can exit AUTH_FAIL instead of restarting in a loop.
        self.auth_failed: bool = False

    async def run(self) -> None:
        """Pump loop — long-poll, filter, enqueue. Returns on auth failure or cancel."""
        offset: int | None = None
        backoff = _BACKOFF_INITIAL_SECONDS
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=offset,
                    timeout=_LONG_POLL_TIMEOUT_SECONDS,
                    allowed_updates=["message", "callback_query"],
                )
                backoff = _BACKOFF_INITIAL_SECONDS
            except TelegramUnauthorizedError as exc:
                logger.error("Telegram rejected the bot token: %s", exc)
                self.auth_failed = True
                return
            except TelegramAPIError as exc:
                logger.warning(
                    "Telegram API error in long-poll (retrying in %.1fs): %s",
                    backoff, exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP_SECONDS)
                continue
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "Unexpected error in long-poll (retrying in %.1fs)", backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP_SECONDS)
                continue

            for update in updates:
                offset = update.update_id + 1
                self._handle_update(update)

            self._maybe_flush_drop_log()

    def _handle_update(self, update: Any) -> None:
        """Filter and enqueue a single update."""
        payload = update_to_dict(update)
        if payload is None:
            return
        if payload["from_user_id"] not in self._allowed:
            self._drop_counts[payload["from_user_id"]] = (
                self._drop_counts.get(payload["from_user_id"], 0) + 1
            )
            return
        self.queue.put_nowait(payload)

    def _maybe_flush_drop_log(self) -> None:
        """Emit aggregate drop counts once per window."""
        now = time.monotonic()
        if now - self._drop_window_started_at < _DROP_LOG_INTERVAL_SECONDS:
            return
        if self._drop_counts:
            for user_id, count in sorted(self._drop_counts.items()):
                logger.warning(
                    "dropped %d unauthorized message(s) from user_id=%d "
                    "in the last %.0fs",
                    count, user_id, _DROP_LOG_INTERVAL_SECONDS,
                )
            self._drop_counts.clear()
        self._drop_window_started_at = now
