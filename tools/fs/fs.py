import os
from typing import List, Dict

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
