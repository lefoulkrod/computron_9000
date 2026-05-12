"""Migration 005: Add provider field to agent profiles.

Profiles created before multi-provider support have no ``provider`` field.
This stamps every such profile with the system-wide ``llm_provider`` from
settings (falling back to ``ollama``), so each profile resolves to a
provider on its own.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import PROFILES_SUBDIR

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"


def _default_provider(state_dir: Path) -> str:
    """Read the system-wide provider from settings.json, defaulting to ollama."""
    path = state_dir / _SETTINGS_FILE
    if not path.exists():
        return "ollama"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "ollama"
    return data.get("llm_provider", "ollama")


def migrate(state_dir: Path) -> None:
    """Set ``provider`` on every profile JSON file that lacks one."""
    profiles_dir = state_dir / PROFILES_SUBDIR
    if not profiles_dir.is_dir():
        return

    provider = _default_provider(state_dir)
    migrated = 0
    for path in profiles_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not data.get("provider"):
            data["provider"] = provider
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            migrated += 1

    if migrated:
        logger.info("Set provider='%s' on %d profile(s)", provider, migrated)
