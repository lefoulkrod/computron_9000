"""Migration 005: Move from a single global LLM provider to per-use providers.

Before multi-provider support:

- ``settings.json`` had a flat ``llm_provider`` / ``llm_base_url``;
- agent profiles had no ``provider`` field;
- the title and compaction models/options came from ``config.yaml``'s
  (now removed) ``summary:`` block.

This migration:

- creates a ``direct_providers`` entry for the old provider when it was a
  direct-connect kind (Ollama, no-auth OpenAI-compatible);
- seeds ``vision_provider`` / ``compaction_provider`` / ``title_provider``
  from the old global provider, and ``title_model`` from the existing main
  model (``compaction_model``), so behavior is preserved;
- seeds ``compaction_options`` from the old ``config.yaml`` ``summary:``
  defaults (that block is gone, so the values are carried as a snapshot);
- drops the legacy ``llm_provider`` / ``llm_base_url`` keys;
- stamps every agent profile with the old global provider.

Brokered providers (OpenAI, Anthropic, OpenRouter, authed compat) already
have their integration in the vault, so nothing to create for them.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import PROFILES_SUBDIR

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"

# Direct-connect provider kinds — these need a base_url and no broker.
_DIRECT_KINDS = {"ollama", "openai_compat"}

# Pre-filled default for Ollama when no explicit base_url was stored.
_OLLAMA_DEFAULT_URL = "http://host.docker.internal:11434"

# The old config.yaml ``summary.options`` defaults — carried as a snapshot
# because that block is removed by the time this migration runs.
_LEGACY_COMPACTION_OPTIONS: dict[str, object] = {
    "num_ctx": 32768,
    "num_predict": 8192,
    "temperature": 0.3,
    "top_k": 20,
}


def _migrate_settings(state_dir: Path) -> str | None:
    """Rewrite settings.json to the new shape. Returns the old global provider."""
    path = state_dir / _SETTINGS_FILE
    if not path.exists():
        # No settings yet — _DEFAULTS already has the new keys; wizard fills them.
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Corrupt %s, skipping settings part of migration 005", path)
        return None

    had_legacy = "llm_provider" in data or "llm_base_url" in data
    legacy_provider = data.pop("llm_provider", None)
    legacy_base_url = data.pop("llm_base_url", None)
    changed = had_legacy

    data.setdefault("direct_providers", {})
    if legacy_provider in _DIRECT_KINDS:
        base_url = legacy_base_url or (_OLLAMA_DEFAULT_URL if legacy_provider == "ollama" else None)
        if base_url:
            data["direct_providers"].setdefault(legacy_provider, {"base_url": base_url})
            changed = True

    if legacy_provider:
        for key in ("vision_provider", "compaction_provider", "title_provider"):
            if not data.get(key):
                data[key] = legacy_provider
                changed = True
        # Title generation runs on the install's main model — the same one
        # the wizard wrote to compaction_model. The old config.yaml had a
        # hardcoded kimi-k2.5:cloud here, which silently failed for anyone
        # not on Ollama; don't carry that forward.
        if not data.get("title_model") and data.get("compaction_model"):
            data["title_model"] = data["compaction_model"]
            changed = True

    if not data.get("compaction_options"):
        data["compaction_options"] = dict(_LEGACY_COMPACTION_OPTIONS)
        changed = True

    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Migrated settings.json to per-use provider model")

    return legacy_provider


def _migrate_profiles(state_dir: Path, default_provider: str) -> None:
    """Set ``provider`` on every profile JSON file that lacks one."""
    profiles_dir = state_dir / PROFILES_SUBDIR
    if not profiles_dir.is_dir():
        return

    migrated = 0
    for path in profiles_dir.glob("*.json"):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not profile.get("provider"):
            profile["provider"] = default_provider
            path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            migrated += 1

    if migrated:
        logger.info("Set provider='%s' on %d profile(s)", default_provider, migrated)


def migrate(state_dir: Path) -> None:
    """Convert settings + profiles from the global-provider model to the new one."""
    legacy_provider = _migrate_settings(state_dir)
    _migrate_profiles(state_dir, legacy_provider or "ollama")
