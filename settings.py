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

# The starting shape of settings.json. This is *not* a runtime fallback layer:
# load_settings() returns whatever is on disk verbatim. Instead, _DEFAULTS gets
# baked into the file the first time save_settings() runs (see save_settings),
# so a fresh install's settings.json is born with every key here. Adding a key
# here only affects new installs — existing installs need a migration to write
# the new key onto their already-persisted file.
_DEFAULTS: dict[str, Any] = {
    "setup_complete": False,
    "default_agent": "computron",
    # Direct-connect providers: {name: {"base_url": "..."}}. Brokered
    # providers (with API keys) live in the integrations vault, not here.
    "direct_providers": {},
    "vision_provider": "",
    "vision_model": "",
    "vision_think": False,
    "vision_options": {
        "num_ctx": 60000,
        "num_predict": 512,
        "temperature": 0.3,
        "top_k": 20,
    },
    "compaction_provider": "",
    "compaction_model": "",
    "compaction_options": {
        "num_ctx": 32768,
        "num_predict": 8192,
        "temperature": 0.3,
        "top_k": 20,
    },
    "title_provider": "",
    "title_model": "",
}

# Metadata service IPs that must never be reachable via user-supplied URLs.
_BLOCKED_HOSTS = {"169.254.169.254", "fd00:ec2::254", "metadata.google.internal"}


def _validate_base_url(v: str) -> str:
    """Reject base URLs that aren't http/https or that target a blocked host."""
    parsed = urllib.parse.urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url must use http or https scheme")
    if parsed.hostname in _BLOCKED_HOSTS:
        raise ValueError("base_url targets a blocked endpoint")
    return v


class SettingsUpdate(BaseModel):
    """Allowed fields for a settings PUT request.

    Using ``extra="forbid"`` ensures unknown keys are rejected before
    they can be persisted to settings.json.
    """

    model_config = ConfigDict(extra="forbid")

    setup_complete: bool | None = None
    default_agent: str | None = None
    direct_providers: dict[str, dict[str, Any]] | None = None
    vision_provider: str | None = None
    vision_model: str | None = None
    vision_think: bool | None = None
    vision_options: dict[str, Any] | None = None
    compaction_provider: str | None = None
    compaction_model: str | None = None
    compaction_options: dict[str, Any] | None = None
    title_provider: str | None = None
    title_model: str | None = None

    @field_validator("direct_providers")
    @classmethod
    def _validate_direct_providers(
        cls, v: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]] | None:
        if not v:
            return v
        for name, entry in v.items():
            base_url = entry.get("base_url")
            if not base_url:
                raise ValueError(f"direct provider {name!r} has no base_url")
            _validate_base_url(base_url)
        return v


def _settings_path() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / _SETTINGS_FILE


def load_settings() -> dict[str, Any]:
    """Return the settings dict.

    If settings.json exists, it's returned verbatim — keys absent from the
    file stay absent (no re-merge with _DEFAULTS). That's deliberate: the
    file is the source of truth, and missing-key gaps on old installs are
    closed by migrations, not by silently overlaying current defaults.

    Before the file has ever been written (a brand-new install, pre-wizard)
    this returns a copy of _DEFAULTS.
    """
    path = _settings_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.warning("Failed to read settings file, using defaults")
    return dict(_DEFAULTS)


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Merge ``data`` into the current settings and write atomically to disk.

    On the very first call (no settings.json yet), ``load_settings()``
    returns a copy of ``_DEFAULTS``, so this write produces
    ``{**_DEFAULTS, **data}`` — i.e. the file is created already containing
    every default key. Later calls read the now-complete file and merge in
    ``data``, so it stays complete.
    """
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
