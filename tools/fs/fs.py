import os
import stat
from typing import List, Dict
import glob

def list_directory_contents(path: str) -> Dict[str, object]:
    """
    Tool to list files and directories at a given path. Use this tool whenever the user asks about files, folders, or directory contents.

    Args:
        path (str): The directory path to list contents of.

    Returns:
        dict: A dictionary with the following keys:
            - status (str): "success" if the directory was listed, "error" otherwise.
            - contents (List[str]): List of file and directory names if successful, else an empty list.
            - error_message (str, optional): Human-readable error message if an error occurred.

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
        contents = os.listdir(path)
        return {"status": "success", "contents": contents}
    except Exception as e:
        return {"status": "error", "contents": [], "error_message": str(e)}

def get_path_details(path: str) -> Dict[str, object]:
    """
    Tool to get details about a file or directory at the given path. Use this tool whenever the user asks for information about a specific file or directory (such as type, size, permissions, etc).

    Args:
        path (str): The file or directory path to get details for.

    Returns:
        dict: A dictionary with the following keys:
            - status (str): "success" if details were retrieved, "error" otherwise.
            - details (dict): Dictionary with details about the path (type, size, permissions, etc) if successful, else empty dict.
            - error_message (str, optional): Human-readable error message if an error occurred.

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
        st = os.stat(path)
        if os.path.isdir(path):
            type_ = "directory"
        elif os.path.isfile(path):
            type_ = "file"
        elif os.path.islink(path):
            type_ = "symlink"
        else:
            type_ = "other"
        permissions = stat.filemode(st.st_mode)
        details = {
            "type": type_,
            "size": st.st_size,
            "permissions": permissions,
            "modified": st.st_mtime,
            "created": st.st_ctime
        }
        return {"status": "success", "details": details}
    except Exception as e:
        return {"status": "error", "details": {}, "error_message": str(e)}

def read_file_contents(path: str) -> Dict[str, object]:
    """
    Tool to read the contents of a file at the given path. Use this tool whenever the user asks to view or read a file's contents.

    Args:
        path (str): The file path to read.

    Returns:
        dict: A dictionary with the following keys:
            - status (str): "success" if the file was read, "error" otherwise.
            - contents (str): The contents of the file (decoded as UTF-8) if successful, else an empty string.
            - error_message (str, optional): Human-readable error message if an error occurred.

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
        with open(path, 'r', encoding='utf-8') as f:
            contents = f.read()
        return {"status": "success", "contents": contents}
    except Exception as e:
        return {"status": "error", "contents": "", "error_message": str(e)}

def search_files(pattern: str) -> Dict[str, object]:
    """
    Tool to search for files and directories using a glob pattern (wildcards). Use this tool whenever the user asks to search for files.

    Args:
        pattern (str): The glob pattern to search for (e.g., '*.txt', 'folder/**/*.py').

    Returns:
        dict: A dictionary with the following keys:
            - status (str): "success" if the search was performed, "error" otherwise.
            - matches (List[str]): List of matching file and directory paths if successful, else an empty list.
            - error_message (str, optional): Human-readable error message if an error occurred.

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
        matches = glob.glob(pattern, recursive=True)
        return {"status": "success", "matches": matches}
    except Exception as e:
        return {"status": "error", "matches": [], "error_message": str(e)}
