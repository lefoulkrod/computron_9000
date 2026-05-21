"""One-shot supervisor maintenance tasks (filesystem perms, etc.).

Separate from the app-server-side ``migrations/`` framework because those
migrations run as the computron uid, which can't ``chmod`` broker-owned
files (the kernel only lets the owner or root change a file's mode). The
supervisor runs as the broker uid → it can. Each task records its name in
a sentinel JSON in the vault dir so it never re-runs after first apply.

Add a new task by:

1. Implement the heal function. Make it idempotent (no-op when current
   state already matches the target) — the sentinel is belt + suspenders.
2. Call it from :func:`run_pending` gated by a unique sentinel name. Use
   a ``_vN`` suffix so a follow-up can ship a ``_v2`` without colliding.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from integrations._perms import AGENT_OWNED_DIR_MODE, AGENT_OWNED_FILE_MODE

logger = logging.getLogger(__name__)

_SENTINEL_FILE = "maintenance.json"


def _load(vault_dir: Path) -> set[str]:
    """Return the set of task names previously applied against ``vault_dir``."""
    path = vault_dir / _SENTINEL_FILE
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, OSError):
        logger.warning("corrupt %s, treating as empty", path)
        return set()


def _save(vault_dir: Path, applied: set[str]) -> None:
    """Persist ``applied`` to the sentinel file as a sorted JSON array."""
    path = vault_dir / _SENTINEL_FILE
    path.write_text(json.dumps(sorted(applied), indent=2), encoding="utf-8")


def _heal_downloads_perms(downloads_dir: Path) -> int:
    """Bring broker-owned entries in ``downloads_dir`` up to the agent-owned modes.

    Earlier releases wrote files at ``0o640`` and left the directory sticky,
    so anything written then is read-only and undeletable to the agent.
    Walk the tree and rewrite the modes — but only for entries owned by the
    supervisor's own uid, so anything the agent wrote in there
    (browser saves, etc.) is left untouched.

    Returns the count of entries whose mode was changed.
    """
    if not downloads_dir.is_dir():
        return 0
    own_uid = os.getuid()
    touched = 0
    for entry in downloads_dir.rglob("*"):
        try:
            st = entry.stat()
        except FileNotFoundError:
            # Tree mutated under us — fine, just skip the gone entry.
            continue
        if st.st_uid != own_uid:
            continue
        target = AGENT_OWNED_DIR_MODE if entry.is_dir() else AGENT_OWNED_FILE_MODE
        if (st.st_mode & 0o7777) == target:
            continue
        try:
            entry.chmod(target)
        except OSError as exc:
            logger.warning("couldn't chmod %s: %s", entry, exc)
            continue
        touched += 1
    return touched


def run_pending(vault_dir: Path, downloads_dir: Path | None) -> None:
    """Apply any one-shot maintenance tasks not yet recorded in the sentinel.

    Safe to call on every supervisor start. Tasks already in the sentinel
    are skipped without further work.
    """
    applied = _load(vault_dir)

    if "heal_downloads_perms_v1" not in applied and downloads_dir is not None:
        n = _heal_downloads_perms(downloads_dir)
        if n:
            logger.info(
                "heal_downloads_perms_v1: chmodded %d broker-owned entr%s in %s",
                n, "y" if n == 1 else "ies", downloads_dir,
            )
        applied.add("heal_downloads_perms_v1")
        _save(vault_dir, applied)
