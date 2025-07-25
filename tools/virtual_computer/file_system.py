"""File system tools for the virtual computer environment.

This module provides utilities for interacting with the file system
within the virtual computer's environment.
"""

import base64
import logging
from pathlib import Path
from typing import TypedDict

from config import load_config

logger = logging.getLogger(__name__)


class WriteFileResult(TypedDict):
    """Return type for write_file_in_home_dir."""

    success: bool
    file_path: str
    error: str | None


def write_file_in_home_dir(path: str, content: str | bytes) -> WriteFileResult:
    """Write content to a file in the virtual computer's home dir, overwriting if it exists.

    Writes a file at the specified path within the virtual computer's home directory.
    Creates parent directories if they do not exist.

    Args:
        path (str): Path to the file to write.
        content (str | bytes): Content to write to the file.

    Returns:
        WriteFileResult: Dict with success True/False and error_code (None if success, str if error).
    """
    file_path: Path | None = None
    try:
        config = load_config()
        home_dir = Path(config.virtual_computer.home_dir)
        rel_path = Path(path)
        file_path = home_dir / rel_path
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            mode = "wb"
            with file_path.open(mode) as f:
                f.write(content)
        elif isinstance(content, str):
            mode = "w"
            with file_path.open(mode, encoding="utf-8") as f:
                f.write(content)
        else:
            logger.error("Content must be of type str or bytes, got %s", type(content))
            return {
                "success": False,
                "file_path": path,
                "error": str(type(content)),
            }
    except Exception as exc:
        logger.exception("Failed to write file at path %s", path)
        return {
            "success": False,
            "file_path": path,
            "error": str(exc),
        }
    logger.debug("Wrote file at path %s", file_path)
    return {"success": True, "file_path": path, "error": None}


class ReadFileError(Exception):
    """Custom exception for errors during file reading operations.

    Args:
        message (str): Error message describing the failure.
    """

    def __init__(self, message: str) -> None:
        """Initialize ReadFileError.

        Args:
            message (str): Error message describing the failure.
        """
        super().__init__(message)


class DirEntry(TypedDict):
    """Directory entry for a file or subdirectory.

    Attributes:
        name (str): The entry's name.
        is_file (bool): True if entry is a file.
        is_dir (bool): True if entry is a directory.
    """

    name: str
    is_file: bool
    is_dir: bool


class FileReadResult(TypedDict):
    """Return type for reading a file."""

    type: str  # always 'file'
    name: str
    content: str
    encoding: str  # 'utf-8' or 'base64'


class DirectoryReadResult(TypedDict):
    """Return type for reading a directory."""

    type: str  # always 'directory'
    name: str
    entries: list["DirEntry"]


type ReadResult = FileReadResult | DirectoryReadResult


def _is_binary_file(file_path: Path) -> bool:
    """Return True if file is binary, False otherwise."""
    try:
        with file_path.open("rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except OSError as exc:
        logger.warning("Could not determine if file is binary: %s", exc)
        return False


async def read_file_or_dir_in_home_dir(path: str | Path) -> ReadResult:
    """Read a file or directory in the virtual computer's home directory.

    Args:
        path (str | Path): Path to the file or directory to read, relative to the virtual home dir.


    Returns:
        FileReadResult or DirectoryReadResult: Typed dict describing the file or directory contents.

    Raises:
        ReadFileError: If reading fails or path does not exist.
    """
    try:
        config = load_config()
        home_dir = Path(config.virtual_computer.home_dir)
        rel_path = Path(path) if not isinstance(path, Path) else path
        target_path = home_dir / rel_path
        if not target_path.exists():
            msg = f"Path does not exist: {target_path}"
            logger.error(msg)
            raise ReadFileError(msg)
        if target_path.is_file():
            if _is_binary_file(target_path):
                with target_path.open("rb") as f:
                    content_bytes = f.read()
                content = base64.b64encode(content_bytes).decode("ascii")
                return {
                    "type": "file",
                    "name": target_path.name,
                    "content": content,
                    "encoding": "base64",
                }
            with target_path.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "type": "file",
                "name": target_path.name,
                "content": content,
                "encoding": "utf-8",
            }
        if target_path.is_dir():
            entries: list[DirEntry] = [
                {
                    "name": entry.name,
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                }
                for entry in target_path.iterdir()
            ]
            return {
                "type": "directory",
                "name": target_path.name,
                "entries": entries,
            }
        msg = f"Path is neither file nor directory: {target_path}"
        logger.error(msg)
        raise ReadFileError(msg)
    except OSError as exc:
        logger.exception("Failed to read file or directory at path %s", path)
        msg = f"Failed to read file or directory: {exc}"
        raise ReadFileError(msg) from exc
