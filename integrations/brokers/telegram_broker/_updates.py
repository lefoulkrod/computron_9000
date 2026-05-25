"""Long-polling update pump.

Pulls updates from Telegram in the background and pushes allowed ones onto
an internal queue. Verb handlers drain the queue via ``next_updates``.

Drops from non-allowlisted senders are silent — replying would confirm the
bot is live and waste outbound rate limits. Drop counts are logged
periodically rather than per-message so a spam burst doesn't spam the log.

Photo and document attachments are downloaded eagerly before the update is
enqueued — the wire shape carries a local path the channel can read.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
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

# Sanitize document filenames before writing — strip path separators and any
# character that isn't safe in a filename. Length-cap so a hostile sender
# can't blow out the directory listing.
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_FILENAME_MAX_LEN = 120


def update_to_dict(update: Any) -> dict[str, Any] | None:
    """Flatten an aiogram ``Update`` to the wire shape, or ``None`` to skip.

    Forwards text/caption ``message`` updates (including photo/document
    attachments) and ``callback_query`` updates. Other update kinds are
    dropped.

    Attachments are returned with metadata + a ``file_id`` placeholder;
    ``UpdatePump`` downloads the bytes asynchronously before the update is
    queued and populates ``path`` on each attachment.
    """
    message = getattr(update, "message", None)
    if message is not None:
        return _message_to_dict(message)
    callback = getattr(update, "callback_query", None)
    if callback is not None:
        return _callback_to_dict(callback)
    return None


def _message_to_dict(message: Any) -> dict[str, Any] | None:
    """Map a ``message`` update to the wire shape.

    A message qualifies for forwarding if it has text, a caption, or at
    least one supported attachment. ``text`` is the user-typed content
    (either ``message.text`` for plain messages or ``message.caption`` when
    a photo/document was sent with explanatory text).
    """
    user = message.from_user
    if user is None:
        return None
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    attachments = _extract_attachment_meta(message)
    if not text and not attachments:
        return None
    payload: dict[str, Any] = {
        "type": "message",
        "message_id": message.message_id,
        "chat_id": message.chat.id,
        "from_user_id": user.id,
        "from_username": getattr(user, "username", None),
        "text": text,
        "is_command": bool(text and text.startswith("/")),
        "timestamp": int(message.date.timestamp()) if message.date else int(time.time()),
    }
    if attachments:
        payload["attachments"] = attachments
    return payload


def _extract_attachment_meta(message: Any) -> list[dict[str, Any]]:
    """Return a list of attachment-metadata dicts for this message.

    Photos arrive as multiple sizes; we keep the largest. Documents arrive
    as a single object with its own filename and mime type. Other kinds
    (voice, video, sticker, animation) are intentionally dropped today.
    """
    out: list[dict[str, Any]] = []

    photos = getattr(message, "photo", None) or []
    if photos:
        # Photo sizes are returned smallest-to-largest; pick the last.
        biggest = photos[-1]
        out.append({
            "kind": "photo",
            "file_id": biggest.file_id,
            "file_unique_id": getattr(biggest, "file_unique_id", ""),
            "file_size": getattr(biggest, "file_size", None),
            "file_name": _photo_filename(biggest),
            "mime_type": "image/jpeg",
            "width": getattr(biggest, "width", None),
            "height": getattr(biggest, "height", None),
        })

    document = getattr(message, "document", None)
    if document is not None:
        out.append({
            "kind": "document",
            "file_id": document.file_id,
            "file_unique_id": getattr(document, "file_unique_id", ""),
            "file_size": getattr(document, "file_size", None),
            "file_name": _safe_filename(
                getattr(document, "file_name", None) or f"document_{document.file_id}",
            ),
            "mime_type": getattr(document, "mime_type", None) or "application/octet-stream",
        })

    return out


def _photo_filename(photo: Any) -> str:
    """Telegram photos have no user-supplied name; derive a stable one."""
    unique = getattr(photo, "file_unique_id", None) or getattr(photo, "file_id", "photo")
    return _safe_filename(f"photo_{unique}.jpg")


def _safe_filename(name: str) -> str:
    """Strip path separators and unsafe characters; cap length."""
    base = Path(name).name  # drop any leading path
    cleaned = _FILENAME_UNSAFE.sub("_", base).strip("._") or "file"
    return cleaned[:_FILENAME_MAX_LEN]


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
        downloads_dir: Path,
    ) -> None:
        self._bot = bot
        self._allowed = allowed_user_ids
        self._integration_id = integration_id
        self._downloads_dir = downloads_dir
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
                await self._handle_update(update)

            self._maybe_flush_drop_log()

    async def _handle_update(self, update: Any) -> None:
        """Filter, download any attachments, and enqueue a single update."""
        payload = update_to_dict(update)
        if payload is None:
            return
        if payload["from_user_id"] not in self._allowed:
            self._drop_counts[payload["from_user_id"]] = (
                self._drop_counts.get(payload["from_user_id"], 0) + 1
            )
            return
        if payload.get("attachments"):
            await self._download_attachments(payload)
        self.queue.put_nowait(payload)

    async def _download_attachments(self, payload: dict[str, Any]) -> None:
        """Download each attachment's bytes; populate ``path`` on each.

        Failures drop the attachment from the wire shape rather than the
        whole message — the agent still gets the text/caption and any
        successful peers.
        """
        kept: list[dict[str, Any]] = []
        for att in payload["attachments"]:
            try:
                local_path = await self._download_one(att)
            except Exception:
                logger.exception(
                    "telegram attachment download failed  file_id=%s  kind=%s",
                    att.get("file_id"), att.get("kind"),
                )
                continue
            att["path"] = str(local_path)
            att.pop("file_id", None)  # drop the internal handle from the wire shape
            kept.append(att)
        payload["attachments"] = kept

    async def _download_one(self, att: dict[str, Any]) -> Path:
        """Pull the file's bytes from Telegram into the downloads dir."""
        file_id = att["file_id"]
        file_name = att["file_name"]
        tg_file = await self._bot.get_file(file_id)
        dest = self._downloads_dir / file_name
        # If the dir doesn't exist yet, create it — the supervisor's
        # entrypoint normally sets perms but be defensive.
        dest.parent.mkdir(parents=True, exist_ok=True)
        await self._bot.download(tg_file, destination=dest)
        return dest

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
