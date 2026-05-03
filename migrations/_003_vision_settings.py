"""Migration 003: Move vision inference options into settings.json.

Previously ``vision.think`` and ``vision.options`` lived in ``config.yaml``.
They now live in settings (user-editable via the UI). This migration seeds
the existing on-disk settings file with the previous config.yaml defaults,
so existing installs pick up the same behavior they had before.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"

# Defaults that used to live in config.yaml: vision
_LEGACY_VISION_THINK = False
_LEGACY_VISION_OPTIONS: dict[str, object] = {
    "num_ctx": 60000,
    "num_predict": 512,
    "temperature": 0.3,
    "top_k": 20,
}


def migrate(state_dir: Path) -> None:
    """Seed vision_think / vision_options in settings.json if absent."""
    path = state_dir / _SETTINGS_FILE
    if not path.exists():
        # No settings file yet — defaults in settings.py will apply on first read.
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Corrupt %s, skipping migration 003", path)
        return

    changed = False
    if "vision_think" not in data:
        data["vision_think"] = _LEGACY_VISION_THINK
        changed = True
    if "vision_options" not in data:
        data["vision_options"] = dict(_LEGACY_VISION_OPTIONS)
        changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Seeded vision inference settings in %s", path)
