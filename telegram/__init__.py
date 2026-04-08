"""Telegram channel — receives messages from Telegram chats and processes
them through the agent pipeline, returning results inline.
"""

from telegram._formatter import TelegramFormatter
from telegram._runner import TelegramChannel
from telegram._state import ConversationMap

__all__ = [
    "TelegramChannel",
    "TelegramFormatter",
    "ConversationMap",
]