"""Search operations: grep across files in the current workspace.

Skips binary files; returns structured matches suitable for LLM consumption.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable
    from pathlib import Path

from ._fs_internal import is_binary_file
from ._path_utils import resolve_under_home
from .models import GrepMatch, GrepResult

logger = logging.getLogger(__name__)


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _apply_globs(
    paths: Iterable[Path],
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
) -> Iterable[Path]:
    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return str(p)

    for p in paths:
        rp = rel(p)
        if include and not any(fnmatch.fnmatch(rp, pat) for pat in include):
            continue
        if exclude and any(fnmatch.fnmatch(rp, pat) for pat in exclude):
            continue
        yield p


def grep(
    pattern: str,
    *,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    regex: bool = True,
    case_sensitive: bool = False,
    max_results: int | None = 1000,
) -> GrepResult:
    """Search files in the current workspace for a pattern.

    Args:
        pattern: Regex or literal pattern to search for.
        include_globs: Optional list of glob patterns to include (relative to workspace root).
        exclude_globs: Optional list of glob patterns to exclude.
            Default excludes are always applied.
        regex: Treat pattern as regex (default). If False, search literally.
        case_sensitive: If True, matches are case-sensitive; default False (case-insensitive).
        max_results: Maximum number of matches to return; None for unlimited.

    Returns:
        GrepResult: Structured matches and counters; ``truncated`` is True when max_results hit.
    """
    try:
        # Default excludes that are always applied
        default_excludes = [".git/**", "node_modules/**", "__pycache__/**", "*.lock"]

        # Merge default excludes with user-provided excludes
        if exclude_globs is None:
            exclude_globs = default_excludes
        else:
            exclude_globs = exclude_globs + default_excludes

        # Root is the home/workspace directory path of '.'
        root_abs, _home, root_rel = resolve_under_home(".")
        if not root_abs.exists() or not root_abs.is_dir():
            return GrepResult(
                success=False,
                matches=[],
                truncated=False,
                searched_files=0,
                error="workspace not found",
            )

        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE
        patt = re.compile(pattern if regex else re.escape(pattern), flags)

        matches: list[GrepMatch] = []
        searched = 0
        for fpath in _apply_globs(_iter_files(root_abs), root_abs, include_globs, exclude_globs):
            try:
                if is_binary_file(fpath):
                    continue
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover - defensive
                logger.warning("Skipping unreadable file %s", fpath)
                continue
            searched += 1
            for i, line in enumerate(text.splitlines(keepends=False), start=1):
                for m in patt.finditer(line):
                    rel_path = (
                        str(fpath.relative_to(root_abs))
                        if fpath.is_relative_to(root_abs)
                        else str(fpath)
                    )
                    matches.append(
                        GrepMatch(
                            file_path=(f"{root_rel}/{rel_path}" if root_rel else rel_path),
                            line_number=i,
                            line=line,
                            start_col=m.start(),
                            end_col=m.end(),
                        )
                    )
                    if max_results is not None and len(matches) >= max_results:
                        return GrepResult(
                            success=True,
                            matches=matches,
                            truncated=True,
                            searched_files=searched,
                        )

        return GrepResult(success=True, matches=matches, truncated=False, searched_files=searched)
    except OSError:  # pragma: no cover - defensive
        logger.exception("grep failed")
        return GrepResult(
            success=False,
            matches=[],
            truncated=False,
            searched_files=0,
            error="grep failed",
        )
