"""Migration 002: Install default agent profiles.

Copies the shipped default profiles from ``agents/default_profiles/``
to ``{state_dir}/agent_profiles/``. Only copies files that don't
already exist on disk — user-modified profiles are not overwritten.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import PROFILES_SUBDIR

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent.parent / "agents" / "default_profiles"


def migrate(state_dir: Path) -> None:
    """Copy shipped default profiles to the state directory."""
    if not _DEFAULT_PROFILES_DIR.is_dir():
        logger.warning("Default profiles directory not found: %s", _DEFAULT_PROFILES_DIR)
        return

    dest = state_dir / PROFILES_SUBDIR
    dest.mkdir(parents=True, exist_ok=True)

    installed = 0
    for src_file in _DEFAULT_PROFILES_DIR.glob("*.json"):
        dst_file = dest / src_file.name
        if dst_file.exists():
            continue
        data = json.loads(src_file.read_text(encoding="utf-8"))
        dst_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        installed += 1
        logger.info("Installed default profile: %s", src_file.stem)

    logger.info("Installed %d default profile(s)", installed)
