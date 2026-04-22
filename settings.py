"""Application settings — runtime user state persisted as JSON.

Unlike ``config`` (static YAML shipped with the app), settings are
mutable state that the user changes at runtime (e.g. via the setup
wizard or the settings page).
"""

import json
import logging
from pathlib import Path
from typing import Any

from config import load_config

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"

_DEFAULTS: dict[str, Any] = {
    "setup_complete": False,
    "default_agent": "computron",
    "vision_model": "",
    "vision_think": False,
    "vision_options": {
        "num_ctx": 60000,
        "num_predict": 512,
        "temperature": 0.3,
        "top_k": 20,
    },
    "compaction_model": "",
}


def _settings_path() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / _SETTINGS_FILE


def load_settings() -> dict[str, Any]:
    """Load settings from disk. Returns defaults if file doesn't exist."""
    path = _settings_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.warning("Failed to read settings file, using defaults")
    return dict(_DEFAULTS)


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Merge data into settings and write to disk."""
    current = load_settings()
    current.update(data)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2))
    return current


__all__ = ["load_settings", "save_settings"]
