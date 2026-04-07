"""Bidirectional Telegram bot interface.

Receives messages from Telegram chats and processes them through the
agent pipeline, returning results inline.  Mirrors the TaskRunner /
TaskExecutor pattern used by the scheduled-tasks system.
"""

from telegram_bot._executor import TelegramTurnExecutor
from telegram_bot._formatter import TelegramFormatter
from telegram_bot._runner import TelegramBotRunner
from telegram_bot._state import ConversationMap

__all__ = [
    "TelegramBotRunner",
    "TelegramTurnExecutor",
    "TelegramFormatter",
    "ConversationMap",
]