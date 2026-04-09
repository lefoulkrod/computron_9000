"""Telegram push notifications for goal run completion/failure."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from config import NotificationsConfig

logger = logging.getLogger(__name__)

_TELEGRAM_MSG_LIMIT = 4096


class TelegramNotifier:
    """Sends messages and file attachments to Telegram via the Bot API.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment variables.
    If either is missing, the notifier disables itself with a warning.
    All public methods are fire-and-forget — errors are logged, never raised.
    """

    def __init__(self, config: NotificationsConfig) -> None:
        self._config = config
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not self._chat_id:
            logger.warning(
                "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — "
                "Telegram notifications disabled"
            )
            self._disabled = True
            self._base_url = ""
            return
        self._disabled = False
        self._base_url = f"https://api.telegram.org/bot{token}"

    @property
    def enabled(self) -> bool:
        return not self._disabled

    async def send(
        self,
        message: str,
        attachments: list[Path] | None = None,
    ) -> None:
        """Send a text message and optional file attachments to Telegram."""
        if self._disabled:
            return
        try:
            await self._send_message(message)
            for path in attachments or []:
                await self._send_document(path)
        except Exception:
            logger.exception("Failed to send Telegram notification")

    async def _send_message(self, text: str) -> None:
        if len(text) > _TELEGRAM_MSG_LIMIT:
            text = text[: _TELEGRAM_MSG_LIMIT - 30] + "\n\n… (truncated)"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                },
            )
            if resp.status_code != 200:
                logger.error(
                    "Telegram sendMessage failed (%d): %s",
                    resp.status_code,
                    resp.text,
                )

    async def _send_document(self, path: Path) -> None:
        max_bytes = self._config.max_attachment_size_mb * 1024 * 1024
        if not path.is_file():
            logger.warning("Attachment not found, skipping: %s", path)
            return
        if path.stat().st_size > max_bytes:
            logger.warning(
                "Attachment too large (%d MB limit), skipping: %s",
                self._config.max_attachment_size_mb,
                path,
            )
            return
        # Read file content in thread to avoid blocking the event loop
        content = await asyncio.to_thread(path.read_bytes)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/sendDocument",
                data={"chat_id": self._chat_id},
                files={"document": (path.name, content)},
            )
            if resp.status_code != 200:
                logger.error(
                    "Telegram sendDocument failed (%d): %s",
                    resp.status_code,
                    resp.text,
                )


def format_run_completed(
    goal_description: str,
    run_number: int,
    duration: str,
    total_tasks: int,
    completed_tasks: int,
    final_output: str,
    file_count: int,
) -> str:
    """Format a success notification message."""
    lines = [
        f"\u2705 Goal completed: {goal_description}",
        f"Run #{run_number} \u00b7 {duration} \u00b7 {completed_tasks}/{total_tasks} tasks",
        "",
    ]
    if final_output:
        lines.append("Final output:")
        lines.append(final_output)
        lines.append("")
    if file_count:
        label = "file" if file_count == 1 else "files"
        lines.append(f"\U0001f4ce {file_count} {label} attached")
    return "\n".join(lines)


def format_run_failed(
    goal_description: str,
    run_number: int,
    duration: str,
    total_tasks: int,
    completed_tasks: int,
    failed_task_description: str,
    error: str,
) -> str:
    """Format a failure notification message."""
    lines = [
        f"\u274c Goal failed: {goal_description}",
        f"Run #{run_number} \u00b7 {duration} \u00b7 {completed_tasks}/{total_tasks} tasks completed",
        "",
        f"Error (task: {failed_task_description}):",
        error,
    ]
    return "\n".join(lines)


__all__ = ["TelegramNotifier", "format_run_completed", "format_run_failed"]
