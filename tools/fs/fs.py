# Standard library imports
"""Utility functions for interacting with the local filesystem."""
import stat
from pathlib import Path
from typing import Any, Literal

# Third-party imports
from pydantic import BaseModel


class BaseFSResult(BaseModel):
    """Base result model for filesystem operations."""

    status: Literal["success", "error"]
    error_message: str | None = None


class DirectoryContents(BaseFSResult):
    """Result model for directory listings."""

    contents: list[str]


class PathDetails(BaseFSResult):
    """Result model describing a filesystem path."""

    details: dict[str, Any]


class FileContents(BaseFSResult):
    """Result model containing file contents."""

    contents: str


class SearchResults(BaseFSResult):
    """Result model for glob searches."""

    matches: list[str]


class WriteResults(BaseFSResult):
    """Result model for file write operations."""

    pass


def list_directory_contents(path: str) -> DirectoryContents:
    """
    List files and directories at a given path.

    Args:
        path (str): The directory path to list contents of.

    Returns:
        DirectoryContents: Result of the directory listing operation.

    Example:
        {
            "status": "success",
            "contents": ["file1.txt", "subdir", ...]
        }
        or
        {
            "status": "error",
            "contents": [],
            "error_message": "Directory not found."
        }
    """
    try:
        path_obj = Path(path)
        contents = [item.name for item in path_obj.iterdir()]
        return DirectoryContents(status="success", contents=contents)
    except Exception as e:
        return DirectoryContents(status="error", contents=[], error_message=str(e))


def get_path_details(path: str) -> PathDetails:
    """
    Get details about a file or directory at the given path.

    Args:
        path (str): The file or directory path to get details for.

    Returns:
        PathDetails: Result of the path details operation.

    Example:
        {
            "status": "success",
            "details": {
                "type": "file",
                "size": 1024,
                "permissions": "rw-r--r--",
                "modified": 1717843200.0
            }
        }
        or
        {
            "status": "error",
            "details": {},
            "error_message": "Path not found."
        }
    """
    try:
        path_obj = Path(path)
        st = path_obj.stat()
        if path_obj.is_dir():
            type_ = "directory"
        elif path_obj.is_file():
            type_ = "file"
        elif path_obj.is_symlink():
            type_ = "symlink"
        else:
            type_ = "other"
        permissions = stat.filemode(st.st_mode)
        details = {
            "type": type_,
            "size": st.st_size,
            "permissions": permissions,
            "modified": st.st_mtime,
            "created": st.st_ctime,
        }
        return PathDetails(status="success", details=details)
    except Exception as e:
        return PathDetails(status="error", details={}, error_message=str(e))


def read_file_contents(path: str) -> FileContents:
    """
    Read the contents of a file at the given path.

    Args:
        path (str): The file path to read.

    Returns:
        FileContents: Result of the file read operation.

    Note:
        The file is always read and returned as UTF-8 text. If the file is not valid UTF-8, an error will be returned.

    Example:
        {
            "status": "success",
            "contents": "file contents here..."
        }
        or
        {
            "status": "error",
            "contents": "",
            "error_message": "File not found."
        }
    """
    try:
        path_obj = Path(path)
        with path_obj.open(encoding="utf-8") as f:
            contents = f.read()
        return FileContents(status="success", contents=contents)
    except Exception as e:
        return FileContents(status="error", contents="", error_message=str(e))


def search_files(pattern: str) -> SearchResults:
    """
    Search for files and directories using a glob pattern (wildcards).

    Args:
        pattern (str): The glob pattern to search for (e.g., '*.txt', 'folder/**/*.py').

    Returns:
        SearchResults: Result of the search operation.

    Example:
        {
            "status": "success",
            "matches": ["foo.txt", "bar/baz.py", ...]
        }
        or
        {
            "status": "error",
            "matches": [],
            "error_message": "No matches found."
        }
    """
    try:
        # Handle recursive patterns properly with Path.rglob for ** patterns
        if "**" in pattern:
            # For recursive patterns, use rglob
            base_pattern = (
                pattern.split("**/")[-1]
                if "**/" in pattern
                else pattern.replace("**", "*")
            )
            path_matches = list(Path().rglob(base_pattern))
        else:
            path_matches = list(Path().glob(pattern))
        # Convert Path objects to strings for compatibility
        matches = [str(match) for match in path_matches]
        return SearchResults(status="success", matches=matches)
    except Exception as e:
        return SearchResults(status="error", matches=[], error_message=str(e))


def write_text_file(contents: str, filename: str) -> WriteResults:
    """
    Write text to a file with the given filename.

    Args:
        contents (str): The string content to write to the file.
        filename (str): The name of the file to create or overwrite.

    Returns:
        WriteResults: Result of the write operation with status and error_message.
    """
    try:
        file_path = Path("/home/larry/.computron_9000") / filename
        with file_path.open("w", encoding="utf-8") as f:
            f.write(contents)
        return WriteResults(status="success")
    except Exception as e:
        return WriteResults(status="error", error_message=str(e))
