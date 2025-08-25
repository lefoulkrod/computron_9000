"""Search operations: grep across files in the current workspace.

Skips binary files; returns structured matches suitable for LLM consumption.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
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


def _expand_globstar_zero_depth(pattern: str) -> set[str]:
    """Expand a pattern so that each "**/" can also be zero directories.

    Example: "src/**/*.js" -> {"src/**/*.js", "src/*.js"}
    Works for multiple occurrences by generating all combinations.
    """
    pat = pattern.replace("\\", "/")
    token = "**/"
    if token not in pat:
        return {pat}
    parts = pat.split(token)
    # Reconstruct with either token kept or removed at each junction
    variants: set[str] = set()
    n = len(parts) - 1
    # Each bit in mask: 1 means keep token, 0 means drop
    for mask in range(1 << n):
        s = parts[0]
        for i in range(n):
            s += (token if (mask & (1 << i)) else "") + parts[i + 1]
        variants.add(s)
    return variants


def _apply_globs(
    paths: Iterable[Path],
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
) -> Iterable[Path]:
    """Filter paths by include/exclude patterns using Path.glob (globstar-on).

    We expand include and exclude patterns using ``root.glob`` which supports
    ``**`` for recursive matches. Only files are considered.
    """
    # Build sets of included/excluded file Paths for fast membership checks
    included: set[Path] | None = None
    excluded: set[Path] = set()

    if include:
        inc_set: set[Path] = set()
        for pat in include:
            for expanded in _expand_globstar_zero_depth(pat):
                for gp in root.glob(expanded):
                    if gp.is_file():
                        inc_set.add(gp)
                    elif gp.is_dir():
                        for fp in gp.rglob("*"):
                            if fp.is_file():
                                inc_set.add(fp)
        included = inc_set

    if exclude:
        for pat in exclude:
            for expanded in _expand_globstar_zero_depth(pat):
                for gp in root.glob(expanded):
                    if gp.is_file():
                        excluded.add(gp)
                    elif gp.is_dir():
                        for fp in gp.rglob("*"):
                            if fp.is_file():
                                excluded.add(fp)

    for p in paths:
        if included is not None and p not in included:
            continue
        if p in excluded:
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
        include_globs: Glob patterns relative to the workspace root that select which files
            to search. Glob semantics follow Bash "globstar on":
            - ``*`` and ``?`` do NOT match ``/`` (directory separators).
            - ``**`` matches zero or more directories recursively.
            - Patterns are matched against the path relative to the workspace root using
              POSIX-style slashes. Examples: ``src/*.py`` (top-level only), ``src/**/*.py``
              (top-level and nested), ``*.py`` (workspace root), ``**/*.py`` (any depth).
            If omitted, all non-excluded files are searched.
        exclude_globs: Glob patterns to exclude from search. Same semantics as include_globs.
            Default excludes are always applied in addition to any provided here.
        regex: Treat pattern as regex (default). If False, search literally.
        case_sensitive: If True, matches are case-sensitive; default False (case-insensitive).
        max_results: Maximum number of matches to return; None for unlimited.

    Returns:
        GrepResult: Structured matches and counters; ``truncated`` is True when max_results hit.
    """
    try:
        # Default excludes that are always applied (globstar semantics)
        default_excludes = [
            ".git/**",
            "node_modules/**",
            "__pycache__/**",
            "**/*.lock",
        ]

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
