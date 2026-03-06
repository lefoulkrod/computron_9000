"""High-level file system operations (write/read/move/etc)."""

from __future__ import annotations

import base64
import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from tools._truncation import truncate_args

from ._fs_internal import is_binary_file
from ._path_utils import resolve_under_home
from .models import (
    DirectoryReadResult,
    DirEntry,
    FileReadResult,
    MakeDirsResult,
    MoveCopyResult,
    PathExistsResult,
    ReadFileError,
    ReadResult,
    RemovePathResult,
    WriteFileResult,
)

logger = logging.getLogger(__name__)


@truncate_args(content=0)
def write_file(path: str, content: str) -> WriteFileResult:
    """Write UTF-8 text to a file, creating parent directories as needed.

    Args:
        path: File path (relative or absolute under home).
        content: Text to write.

    Returns:
        WriteFileResult: Success flag and relative ``file_path``.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to write file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error=str(exc))
    logger.debug("Wrote file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


def make_dirs(path: str) -> MakeDirsResult:
    """Create a directory and any missing parents.

    Args:
        path: Directory path (relative or absolute under home).

    Returns:
        MakeDirsResult: Success flag and relative ``dir_path``.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        abs_path.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to create directories at path %s", path)
        return MakeDirsResult(success=False, dir_path=path, error="mkdir failed")
    else:
        return MakeDirsResult(success=True, dir_path=rel)


def remove_path(path: str) -> RemovePathResult:
    """Remove a file or directory (recursive). No-op if path doesn't exist.

    Args:
        path: Path to remove (relative or absolute under home).

    Returns:
        RemovePathResult: Success flag and relative ``path``.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists():
            return RemovePathResult(success=True, path=rel)
        if abs_path.is_file() or abs_path.is_symlink():
            abs_path.unlink(missing_ok=True)
        elif abs_path.is_dir():
            shutil.rmtree(abs_path)
        else:
            return RemovePathResult(success=False, path=rel, error="Unsupported path type")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to remove path %s", path)
        return RemovePathResult(success=False, path=path, error="remove failed")
    else:
        return RemovePathResult(success=True, path=rel)


def move_path(src: str, dst: str) -> MoveCopyResult:
    """Move a file or directory, creating destination parents as needed.

    Args:
        src: Source path (relative or absolute under home).
        dst: Destination path (relative or absolute under home).

    Returns:
        MoveCopyResult: Success flag with relative ``src`` and ``dst``.
    """
    try:
        src_abs, _home, src_rel = resolve_under_home(src)
        dst_abs, _home2, dst_rel = resolve_under_home(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_abs), str(dst_abs))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to move path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="move failed")
    else:
        return MoveCopyResult(success=True, src=src_rel, dst=dst_rel)


def copy_path(src: str, dst: str) -> MoveCopyResult:
    """Copy a file or directory (recursive, merges into existing dirs).

    Args:
        src: Source path (relative or absolute under home).
        dst: Destination path (relative or absolute under home).

    Returns:
        MoveCopyResult: Success flag with relative ``src`` and ``dst``.
    """
    try:
        src_abs, _home, src_rel = resolve_under_home(src)
        dst_abs, _home2, dst_rel = resolve_under_home(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if src_abs.is_dir():
            shutil.copytree(src_abs, dst_abs, dirs_exist_ok=True)
        else:
            shutil.copy2(src_abs, dst_abs)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to copy path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="copy failed")
    else:
        return MoveCopyResult(success=True, src=src_rel, dst=dst_rel)


@truncate_args(content=0)
def append_to_file(path: str, content: str) -> WriteFileResult:
    """Append UTF-8 text to a file, creating the file and parents if needed.

    Args:
        path: File path (relative or absolute under home).
        content: Text to append.

    Returns:
        WriteFileResult: Success flag and relative ``file_path``.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error="append failed")
    logger.debug("Appended to file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


@truncate_args(content=0)
def prepend_to_file(path: str, content: str) -> WriteFileResult:
    """Prepend UTF-8 text to a file, creating the file if needed.

    Args:
        path: Relative or absolute path under the home directory.
        content: Text to prepend (UTF-8). Only ``str`` is accepted.

    Returns:
        WriteFileResult: Indicates success or failure with the relative ``file_path``.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        existing_text = ""
        if file_path.exists():
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    existing_text = f.read()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to read existing file for prepend at path %s", path)
                return WriteFileResult(
                    success=False,
                    file_path=rel_return_path,
                    error="read failed",
                )

        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)
            if existing_text:
                f.write(existing_text)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to prepend file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error="prepend failed")
    logger.debug("Prepended to file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


def write_files(files: list[tuple[str, str]]) -> list[WriteFileResult]:
    """Write multiple text files in a batch.

    Each item is processed independently using ``write_file``.

    Args:
        files: A list of ``(path, content)`` tuples where ``content`` is ``str``
            (written as UTF-8).

    Returns:
        list[WriteFileResult]: A list of results in the same order as inputs.
        Examine individual items for success or error details.
    """
    results: list[WriteFileResult] = []
    for path, content in files:
        results.append(write_file(path, content))
    return results


def path_exists(path: str) -> PathExistsResult:
    """Check whether a path exists and its type (file or directory).

    Args:
        path: Path to check (relative or absolute under home).

    Returns:
        PathExistsResult: ``exists``, ``is_file``, ``is_dir``, and ``path``.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        exists = abs_path.exists()
        is_file = abs_path.is_file()
        is_dir = abs_path.is_dir()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to check existence for path %s", path)
        return PathExistsResult(exists=False, is_file=False, is_dir=False, path=path)
    else:
        return PathExistsResult(exists=exists, is_file=is_file, is_dir=is_dir, path=rel)


def _read_file_directory(path: str) -> ReadResult:
    """Read a file (text or base64) or list a directory.

    Internal function that handles both file reading and directory listing.
    For files, binary files are returned base64-encoded with ``encoding`` set to
    ``"base64"``. Text files are returned decoded as UTF-8 with ``encoding`` set
    to ``"utf-8"``. For directories, returns an entry listing.

    Args:
        path: Relative or absolute path (under the home directory) to read.

    Returns:
        ReadResult: ``FileReadResult`` for files or ``DirectoryReadResult`` for
        directories. The ``name`` is the path relative to the home directory.

    Raises:
        ReadFileError: If the path does not exist, is not readable, or is an
            unsupported type.
    """
    try:
        target_path, _home, rel_return_path = resolve_under_home(path)
        if not target_path.exists():
            msg = f"Path does not exist: {rel_return_path}"
            logger.error(msg)
            raise ReadFileError(msg)
        if target_path.is_file():
            if is_binary_file(target_path):
                with target_path.open("rb") as f:
                    content_bytes = f.read()
                content = base64.b64encode(content_bytes).decode("ascii")
                return FileReadResult(name=rel_return_path, content=content, encoding="base64")
            with target_path.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return FileReadResult(name=rel_return_path, content=content, encoding="utf-8")
        if target_path.is_dir():
            entries: list[DirEntry] = [
                DirEntry(name=entry.name, is_file=entry.is_file(), is_dir=entry.is_dir())
                for entry in target_path.iterdir()
            ]
            return DirectoryReadResult(name=rel_return_path, entries=entries)
        msg = f"Path is neither file nor directory: {rel_return_path}"
        logger.error(msg)
        raise ReadFileError(msg)
    except OSError as exc:  # pragma: no cover - defensive
        logger.exception("Failed to read file or directory at path %s", path)
        msg = "Failed to read file or directory."
        raise ReadFileError(msg) from exc


def list_dir(path: str, *, include_hidden: bool = False) -> DirectoryReadResult:
    """List directory contents.

    Args:
        path: Directory path (relative or absolute under home).
        include_hidden: If False (default), exclude dotfiles/dotdirs.

    Returns:
        DirectoryReadResult: Entries with ``name``, ``is_file``, ``is_dir``.
    """
    result = _read_file_directory(path)

    if not isinstance(result, DirectoryReadResult):
        msg = f"Path is not a directory: {result.name}"
        logger.error(msg)
        raise ReadFileError(msg)

    if include_hidden:
        return result

    # Filter out hidden files/directories (those starting with '.')
    filtered_entries = [entry for entry in result.entries if not entry.name.startswith(".")]

    return DirectoryReadResult(name=result.name, entries=filtered_entries)
