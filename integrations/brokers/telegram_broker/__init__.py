"""Telegram broker — holds the bot token and bridges Telegram's HTTP API
to the broker RPC surface.

The broker process owns the aiogram ``Bot`` instance, runs a long-polling
loop, enforces the per-integration allowlist of sender user IDs, and
exposes a small set of verbs (``next_updates``, ``send_message``,
``get_me``) over the standard UDS RPC framing.
"""
