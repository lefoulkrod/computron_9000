"""Stat-style helpers for simple existence/type checks."""

from __future__ import annotations

import logging
from .file_ops import path_exists
from .models import PathExistsResult

logger = logging.getLogger(__name__)


def exists(path: str) -> PathExistsResult:
    """Check whether a path exists."""
    return path_exists(path)


def is_file(path: str) -> PathExistsResult:
    """Check whether a path is an existing file."""
    return path_exists(path)


def is_dir(path: str) -> PathExistsResult:
    """Check whether a path is an existing directory."""
    return path_exists(path)
