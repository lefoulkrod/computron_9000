"""Stat-style helpers for simple existence/type checks.

Thin LLM-friendly wrappers around path_exists.
"""

from __future__ import annotations

import logging

from .file_ops import path_exists
from .models import PathExistsResult

logger = logging.getLogger(__name__)


def exists(path: str) -> PathExistsResult:
    """Check whether a path exists within the workspace.

    Args:
        path: Relative or absolute path under the virtual computer home.

    Returns:
        PathExistsResult: ``exists``, ``is_file``, ``is_dir``, and normalized ``path``.
    """
    return path_exists(path)


def is_file(path: str) -> PathExistsResult:
    """Check whether a path is an existing file.

    Args:
        path: Relative or absolute path under the virtual computer home.

    Returns:
        PathExistsResult: with flags populated. ``exists`` may be False.
    """
    return path_exists(path)


def is_dir(path: str) -> PathExistsResult:
    """Check whether a path is an existing directory.

    Args:
        path: Relative or absolute path under the virtual computer home.

    Returns:
        PathExistsResult: with flags populated. ``exists`` may be False.
    """
    return path_exists(path)
