"""Migration 004: Rename num_ctx to context_window in agent profiles.

The num_ctx field was Ollama-specific terminology. It's now called
context_window on profiles — a provider-neutral name for the context
limit used by compaction. For Ollama, it's still sent as num_ctx in the
API options; the rename is profile-level only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import PROFILES_SUBDIR

logger = logging.getLogger(__name__)


def migrate(state_dir: Path) -> None:
    """Rename num_ctx → context_window in all profile JSON files."""
    profiles_dir = state_dir / PROFILES_SUBDIR
    if not profiles_dir.is_dir():
        return

    migrated = 0
    for path in profiles_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if "num_ctx" in data:
            data["context_window"] = data.pop("num_ctx")
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            migrated += 1

    if migrated:
        logger.info("Renamed num_ctx → context_window in %d profile(s)", migrated)
