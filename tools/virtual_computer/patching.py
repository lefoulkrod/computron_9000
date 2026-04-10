"""Text patch application utilities (structured + unified diff)."""

import logging
from pathlib import Path

from tools._truncation import truncate_args

from ._fs_internal import is_binary_file, read_text_lines, write_text_lines
from .models import ApplyPatchResult

logger = logging.getLogger(__name__)


@truncate_args(old_text=200, new_text=200)
def apply_text_patch(path: str, old_text: str, new_text: str) -> ApplyPatchResult:
    """Replace a unique block of text in a file with new content.

    The old_text must match exactly one location in the file (character-for-
    character, including whitespace). If it matches zero or multiple locations
    the operation fails with a descriptive error.

    Args:
        path: Target file path.
        old_text: Exact text to find and replace. Must be unique in the file.
        new_text: Replacement text.

    Returns:
        ApplyPatchResult: Success flag, ``file_path``, and unified ``diff``.
    """
    try:
        abs_path = Path(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ApplyPatchResult(success=False, file_path=path, error="File does not exist")
        if is_binary_file(abs_path):
            return ApplyPatchResult(success=False, file_path=path, error="Binary file not supported")

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_text)

        if count == 0:
            return ApplyPatchResult(
                success=False,
                file_path=path,
                error="No match found. Ensure old_text matches the file content exactly, "
                "including whitespace and indentation.",
            )
        if count > 1:
            return ApplyPatchResult(
                success=False,
                file_path=path,
                error=f"Found {count} matches. Include more surrounding context "
                "in old_text to make a unique match.",
            )

        if old_text == new_text:
            return ApplyPatchResult(success=True, file_path=path)

        new_content = content.replace(old_text, new_text, 1)
        write_text_lines(abs_path, new_content.splitlines(keepends=True))
        return ApplyPatchResult(success=True, file_path=path)
    except (OSError, ValueError) as exc:  # pragma: no cover
        logger.exception("Failed to apply text patch to %s", path)
        return ApplyPatchResult(success=False, file_path=path, error=str(exc))


@truncate_args(patch_text=300)
def apply_unified_diff(patch_text: str) -> list[ApplyPatchResult]:
    """Apply unified diff patches to existing text files.

    The given ``patch_text`` may contain hunks for one or more files. File
    creation and deletion are not supported; attempts to patch non-existent
    files yield error results for those entries.

    Args:
        patch_text: Unified diff text covering one or multiple files.

    Returns:
        list[ApplyPatchResult]: One result per file encountered in the diff,
        reporting success and an optional unified diff of the applied changes,
        or an ``error`` message.
    """
    results: list[ApplyPatchResult] = []
    lines = patch_text.splitlines(keepends=False)
    idx = 0
    current_old: str | None = None
    current_new: str | None = None
    hunks: list[tuple[int, int, int, int, list[str]]] = []

    def parse_range(token: str) -> tuple[int, int]:
        if "," in token:
            start_s, count_s = token.split(",", 1)
            return int(start_s), int(count_s)
        return int(token), 1

    def flush_file() -> None:
        nonlocal current_old, current_new, hunks
        if current_new is None:
            return
        target = current_new
        if target.startswith(("a/", "b/")):
            target = target[2:]
        if target == "/dev/null":
            results.append(
                ApplyPatchResult(
                    success=False,
                    file_path=target,
                    error="File creation/deletion not supported",
                )
            )
        else:
            try:
                abs_path = Path(target)
                if not abs_path.exists() or not abs_path.is_file():
                    results.append(
                        ApplyPatchResult(
                            success=False,
                            file_path=target,
                            error="Target file missing",
                        )
                    )
                else:
                    original = read_text_lines(abs_path)
                    try:
                        patched = _apply_hunks(original, hunks)
                    except ValueError as exc:  # pragma: no cover - error path
                        results.append(ApplyPatchResult(success=False, file_path=target, error=str(exc)))
                    else:
                        if original != patched:
                            write_text_lines(abs_path, patched)
                        results.append(
                            ApplyPatchResult(
                                success=True,
                                file_path=target,
                            )
                        )
            except (OSError, ValueError) as exc:  # pragma: no cover
                results.append(ApplyPatchResult(success=False, file_path=target, error=str(exc)))
        current_old = None
        current_new = None
        hunks = []

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("--- ") and idx + 1 < len(lines) and lines[idx + 1].startswith("+++ "):
            flush_file()
            current_old = line.split(maxsplit=1)[1].strip()
            current_new = lines[idx + 1].split(maxsplit=1)[1].strip()
            idx += 2
            continue
        if line.startswith("@@ "):
            header = line
            try:
                parts = header.split()
                old_spec = parts[1]
                new_spec = parts[2]
                if not old_spec.startswith("-") or not new_spec.startswith("+"):
                    msg = "Malformed hunk header"
                    raise ValueError(msg)
                old_start, old_count = parse_range(old_spec[1:])
                new_start, new_count = parse_range(new_spec[1:])
            except (IndexError, ValueError) as exc:
                results.append(ApplyPatchResult(success=False, file_path=current_new or "?", error=str(exc)))
                idx += 1
                continue
            idx += 1
            hunk_body: list[str] = []
            while idx < len(lines):
                l2 = lines[idx]
                if l2.startswith(("@@ ", "--- ")):
                    break
                if l2 and l2[0] in {" ", "+", "-"}:
                    hunk_body.append(l2)
                else:
                    break
                idx += 1
            hunks.append((old_start, old_count, new_start, new_count, hunk_body))
            continue
        idx += 1
    flush_file()
    return results


def _apply_hunks(original: list[str], hunks: list[tuple[int, int, int, int, list[str]]]) -> list[str]:
    """Apply parsed hunks to an original list of lines."""
    result: list[str] = []
    orig_pos = 0
    for old_start, _old_count, _new_start, _new_count, body in hunks:
        pre_index = old_start - 1
        if pre_index < 0:
            msg = "Invalid hunk start"
            raise ValueError(msg)
        if pre_index > len(original):
            msg = "Hunk starts beyond EOF"
            raise ValueError(msg)
        result.extend(original[orig_pos:pre_index])
        orig_line_index = pre_index
        removed = 0
        for line in body:
            tag = line[:1]
            content = line[1:] + "\n" if not line.endswith("\n") else line[1:]
            if tag == " ":
                if orig_line_index >= len(original) or original[orig_line_index] != content:
                    msg = "Context mismatch applying hunk"
                    raise ValueError(msg)
                result.append(content)
                orig_line_index += 1
            elif tag == "-":
                if orig_line_index >= len(original) or original[orig_line_index] != content:
                    msg = "Removal mismatch applying hunk"
                    raise ValueError(msg)
                orig_line_index += 1
                removed += 1
            elif tag == "+":
                result.append(content)
            else:
                msg = "Unknown hunk line prefix"
                raise ValueError(msg)
        orig_pos = orig_line_index
    result.extend(original[orig_pos:])
    return result
