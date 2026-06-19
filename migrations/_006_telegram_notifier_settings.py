"""Migration 006: Add Telegram notifier settings keys.

The goal-run push notifier previously read ``TELEGRAM_INTEGRATION_ID`` and
``TELEGRAM_CHAT_ID`` from the environment. Both now live in
``settings.json`` so the user can edit them in the app's Settings → System
page. This migration seeds the keys with empty defaults on existing
installs; users who relied on the env vars will need to re-enter the
values in the UI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"


def migrate(state_dir: Path) -> None:
    """Add telegram_notifier_* keys to settings.json if absent."""
    path = state_dir / _SETTINGS_FILE
    if not path.exists():
        # No settings file yet — defaults in settings.py will apply on first read.
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Corrupt %s, skipping migration 006", path)
        return

    changed = False
    if "telegram_notifier_integration_id" not in data:
        data["telegram_notifier_integration_id"] = ""
        changed = True
    if "telegram_notifier_chat_id" not in data:
        data["telegram_notifier_chat_id"] = None
        changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Seeded telegram notifier settings in %s", path)
