"""Shared backup helper for migrations.

Migrations that rewrite files should save the original under
``{state_dir}/.backups/{migration_name}/`` preserving the relative
path.  This keeps backups out of the live state tree so they don't get
picked up by globs that walk ``goals/`` or similar directories.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_BACKUPS_DIR = ".backups"


def backup_file(state_dir: Path, migration_name: str, source: Path) -> Path:
    """Back up a file under state_dir/.backups/{migration_name}/.

    The backup preserves the source's path relative to ``state_dir``::

        state_dir/goals/g1.json
        → state_dir/.backups/{migration_name}/goals/g1.json

    Args:
        state_dir: Root of the state directory.
        migration_name: Name of the migration doing the backup.
        source: File to back up (must be inside ``state_dir``).

    Returns:
        The path where the backup was written.
    """
    rel = source.resolve().relative_to(state_dir.resolve())
    dest = state_dir / _BACKUPS_DIR / migration_name / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


__all__ = ["backup_file"]
