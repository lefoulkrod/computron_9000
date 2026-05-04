"""Application settings — runtime user state persisted as JSON.

Unlike ``config`` (static YAML shipped with the app), settings are
mutable state that the user changes at runtime (e.g. via the setup
wizard or the settings page).
"""

import json
import logging
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

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

# Metadata service IPs that must never be reachable via user-supplied URLs.
_BLOCKED_HOSTS = {"169.254.169.254", "fd00:ec2::254", "metadata.google.internal"}


class SettingsUpdate(BaseModel):
    """Allowed fields for a settings PUT request.

    Using ``extra="forbid"`` ensures unknown keys are rejected with a 422
    before they can be persisted to settings.json.
    """

    model_config = ConfigDict(extra="forbid")

    setup_complete: bool | None = None
    default_agent: str | None = None
    vision_model: str | None = None
    vision_model: str | None = None
    vision_think: bool | None = None
    vision_options: dict[str, Any] | None = None
    compaction_model: str | None = None
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None

    @field_validator("llm_base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        if not v:
            return v
        parsed = urllib.parse.urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("llm_base_url must use http or https scheme")
        if parsed.hostname in _BLOCKED_HOSTS:
            raise ValueError("llm_base_url targets a blocked endpoint")
        return v


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
    """Merge data into settings and write atomically to disk."""
    current = load_settings()
    current.update(data)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to a temp file in the same directory, then rename.
    # This prevents a corrupt settings.json if the process is killed mid-write.
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".settings_tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(current, indent=2))
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return current


__all__ = ["load_settings", "save_settings", "SettingsUpdate"]
