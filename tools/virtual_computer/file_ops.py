"""High-level file system operations (write/read/move/etc)."""

from __future__ import annotations

import base64
import logging
import shutil
from pathlib import Path

from tools._truncation import truncate_args

from ._fs_internal import is_binary_file
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
    """Write UTF-8 text to a file, creating parent directories as needed."""
    try:
        file_path = Path(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        logger.exception("Failed to write file at path %s", path)
        return WriteFileResult(success=False, file_path=path, error=str(exc))
    logger.debug("Wrote file at path %s", path)
    return WriteFileResult(success=True, file_path=path)


def make_dirs(path: str) -> MakeDirsResult:
    """Create a directory and any missing parents."""
    try:
        abs_path = Path(path)
        abs_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create directories at path %s", path)
        return MakeDirsResult(success=False, dir_path=path, error="mkdir failed")
    else:
        return MakeDirsResult(success=True, dir_path=path)


def remove_path(path: str) -> RemovePathResult:
    """Remove a file or directory (recursive). No-op if path doesn't exist."""
    try:
        abs_path = Path(path)
        if not abs_path.exists():
            return RemovePathResult(success=True, path=path)
        if abs_path.is_file() or abs_path.is_symlink():
            abs_path.unlink(missing_ok=True)
        elif abs_path.is_dir():
            shutil.rmtree(abs_path)
        else:
            return RemovePathResult(success=False, path=path, error="Unsupported path type")
    except Exception:
        logger.exception("Failed to remove path %s", path)
        return RemovePathResult(success=False, path=path, error="remove failed")
    else:
        return RemovePathResult(success=True, path=path)


def move_path(src: str, dst: str) -> MoveCopyResult:
    """Move a file or directory, creating destination parents as needed."""
    try:
        src_abs = Path(src)
        dst_abs = Path(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_abs), str(dst_abs))
    except Exception:
        logger.exception("Failed to move path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="move failed")
    else:
        return MoveCopyResult(success=True, src=src, dst=dst)


def copy_path(src: str, dst: str) -> MoveCopyResult:
    """Copy a file or directory (recursive, merges into existing dirs)."""
    try:
        src_abs = Path(src)
        dst_abs = Path(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if src_abs.is_dir():
            shutil.copytree(src_abs, dst_abs, dirs_exist_ok=True)
        else:
            shutil.copy2(src_abs, dst_abs)
    except Exception:
        logger.exception("Failed to copy path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="copy failed")
    else:
        return MoveCopyResult(success=True, src=src, dst=dst)


@truncate_args(content=0)
def append_to_file(path: str, content: str) -> WriteFileResult:
    """Append UTF-8 text to a file, creating the file and parents if needed."""
    try:
        file_path = Path(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        logger.exception("Failed to append file at path %s", path)
        return WriteFileResult(success=False, file_path=path, error="append failed")
    logger.debug("Appended to file at path %s", path)
    return WriteFileResult(success=True, file_path=path)


@truncate_args(content=0)
def prepend_to_file(path: str, content: str) -> WriteFileResult:
    """Prepend UTF-8 text to a file, creating the file if needed."""
    try:
        file_path = Path(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        existing_text = ""
        if file_path.exists():
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    existing_text = f.read()
            except Exception:
                logger.exception("Failed to read existing file for prepend at path %s", path)
                return WriteFileResult(
                    success=False,
                    file_path=path,
                    error="read failed",
                )

        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)
            if existing_text:
                f.write(existing_text)
    except Exception:
        logger.exception("Failed to prepend file at path %s", path)
        return WriteFileResult(success=False, file_path=path, error="prepend failed")
    logger.debug("Prepended to file at path %s", path)
    return WriteFileResult(success=True, file_path=path)


def write_files(files: list[tuple[str, str]]) -> list[WriteFileResult]:
    """Write multiple text files in a batch."""
    results: list[WriteFileResult] = []
    for path, content in files:
        results.append(write_file(path, content))
    return results


def path_exists(path: str) -> PathExistsResult:
    """Check whether a path exists and its type (file or directory)."""
    try:
        abs_path = Path(path)
        exists = abs_path.exists()
        is_file = abs_path.is_file()
        is_dir = abs_path.is_dir()
    except Exception:
        logger.exception("Failed to check existence for path %s", path)
        return PathExistsResult(exists=False, is_file=False, is_dir=False, path=path)
    else:
        return PathExistsResult(exists=exists, is_file=is_file, is_dir=is_dir, path=path)


def _read_file_directory(path: str) -> ReadResult:
    """Read a file (text or base64) or list a directory."""
    try:
        target_path = Path(path)
        if not target_path.exists():
            msg = "Path does not exist: %s" % path
            logger.error(msg)
            raise ReadFileError(msg)
        if target_path.is_file():
            if is_binary_file(target_path):
                with target_path.open("rb") as f:
                    content_bytes = f.read()
                content = base64.b64encode(content_bytes).decode("ascii")
                return FileReadResult(name=path, content=content, encoding="base64")
            with target_path.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return FileReadResult(name=path, content=content, encoding="utf-8")
        if target_path.is_dir():
            entries: list[DirEntry] = [
                DirEntry(name=entry.name, is_file=entry.is_file(), is_dir=entry.is_dir())
                for entry in target_path.iterdir()
            ]
            return DirectoryReadResult(name=path, entries=entries)
        msg = "Path is neither file nor directory: %s" % path
        logger.error(msg)
        raise ReadFileError(msg)
    except ReadFileError:
        raise
    except OSError as exc:
        logger.exception("Failed to read file or directory at path %s", path)
        msg = "Failed to read file or directory."
        raise ReadFileError(msg) from exc


def list_dir(path: str, *, include_hidden: bool = False) -> DirectoryReadResult:
    """List directory contents."""
    result = _read_file_directory(path)

    if not isinstance(result, DirectoryReadResult):
        msg = "Path is not a directory: %s" % result.name
        logger.error(msg)
        raise ReadFileError(msg)

    if include_hidden:
        return result

    filtered_entries = [entry for entry in result.entries if not entry.name.startswith(".")]

    return DirectoryReadResult(name=result.name, entries=filtered_entries)
