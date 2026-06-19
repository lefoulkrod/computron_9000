"""Telegram push notifications for goal run completion/failure.

Sends messages through the telegram broker (same broker the bidirectional
channel uses); no Telegram credentials live in this process.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from integrations.broker_client import IntegrationError, call as broker_call
from settings import load_settings

if TYPE_CHECKING:
    from config import NotificationsConfig

logger = logging.getLogger(__name__)

# Matches Telegram's per-message text cap; we truncate locally so the broker
# returns a clean message_id rather than rejecting a 4097-character payload.
_TELEGRAM_MSG_LIMIT = 4096


class TelegramNotifier:
    """Sends notification messages to Telegram via the broker.

    Configuration is read from app settings (``telegram_notifier_integration_id``
    and ``telegram_notifier_chat_id``) on construction. If either is blank,
    the notifier disables itself with a warning. All public methods are
    fire-and-forget — errors are logged, never raised.
    """

    def __init__(
        self,
        config: NotificationsConfig,
        *,
        app_sock_path: Path,
    ) -> None:
        self._config = config
        self._app_sock = app_sock_path
        settings = load_settings()
        self._integration_id = settings.get("telegram_notifier_integration_id") or ""
        chat_id = settings.get("telegram_notifier_chat_id")
        self._chat_id: int | None = chat_id if isinstance(chat_id, int) else None

        if not self._integration_id or self._chat_id is None:
            logger.warning(
                "Telegram notifier integration_id or chat_id not configured — "
                "notifications disabled",
            )
            self._disabled = True
        else:
            self._disabled = False

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
        except Exception:
            logger.exception("Failed to send Telegram notification")
            return

        for path in attachments or []:
            # Document uploads through the broker are pending; surface the
            # skip rather than silently dropping the file references.
            logger.warning(
                "telegram attachment not sent (broker send_document not "
                "implemented yet): %s", path,
            )

    async def _send_message(self, text: str) -> None:
        if len(text) > _TELEGRAM_MSG_LIMIT:
            text = text[: _TELEGRAM_MSG_LIMIT - 30] + "\n\n… (truncated)"
        try:
            await broker_call(
                self._integration_id,
                "send_message",
                {"chat_id": self._chat_id, "text": text},
                app_sock_path=self._app_sock,
            )
        except IntegrationError as exc:
            logger.error("Telegram send_message failed: %s", exc)


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
        f"✅ Goal completed: {goal_description}",
        f"Run #{run_number} · {duration} · {completed_tasks}/{total_tasks} tasks",
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
        f"❌ Goal failed: {goal_description}",
        f"Run #{run_number} · {duration} · {completed_tasks}/{total_tasks} tasks completed",
        "",
        f"Error (task: {failed_task_description}):",
        error,
    ]
    return "\n".join(lines)


__all__ = ["TelegramNotifier", "format_run_completed", "format_run_failed"]
