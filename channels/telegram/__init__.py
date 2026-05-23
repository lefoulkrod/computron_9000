"""Telegram channel — receives messages from Telegram chats and processes
them through the agent pipeline, returning results inline.
"""

from channels.telegram._formatter import TelegramFormatter
from channels.telegram._runner import TelegramChannel
from channels.telegram._state import ConversationMap

__all__ = [
    "ConversationMap",
    "TelegramChannel",
    "TelegramFormatter",
]
