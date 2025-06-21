"""
Module for executing basic Python or Node.js programs in isolated containers.

This tool provides functions to execute code snippets in either Python or Node.js environments using containers. It supports capturing stdout, stderr, and exit codes. Containers are stopped after execution and removed.
"""

import logging
from typing import Dict, List, Optional

from tools.code.container_core import (
    _run_code_in_container,
)

logger = logging.getLogger(__name__)

def execute_python_program(program_text: str, packages: Optional[List[str]] = None) -> Dict[str, Optional[str]]:
    """
    Execute a Python program in a containerized Python 3.12 environment, installing specified packages first.

    Args:
        program_text (str): The Python program to execute.
        packages (Optional[List[str]]): List of pip packages to install before execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails.
    """
    image = "python:3.12-slim"
    filename = "main.py"
    command = ["python", f"/root/{filename}"]
    return _run_code_in_container(
        image=image,
        filename=filename,
        command=command,
        program_text=program_text,
        language="python",
        packages=packages,
    )

def execute_nodejs_program(program_text: str, packages: Optional[List[str]] = None) -> Dict[str, Optional[str]]:
    """
    Execute a Node.js script in a containerized Node.js environment, installing specified packages first.

    Args:
        program_text (str): The Node.js script to execute.
        packages (Optional[List[str]]): List of npm packages to install before execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails.
    """
    image = "playwright:v1.53.1-noble"
    filename = "main.js"
    command = ["node", f"/root/{filename}"]
    return _run_code_in_container(
        image=image,
        filename=filename,
        command=command,
        program_text=program_text,
        language="node",
        packages=packages,
    )

def execute_nodejs_program_with_playwright(program_text: str, packages: Optional[List[str]] = None) -> Dict[str, Optional[str]]:
    """
    Execute a Node.js program in a container with Playwright and browsers preinstalled, suitable for web navigation tasks.

    Args:
        program_text (str): The Node.js script to execute.
        packages (Optional[List[str]]): List of npm packages to install before execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails.
    """
    packages = packages or []
    all_packages = list(set(packages + ["playwright@1.53.1"]))
    return execute_nodejs_program(program_text=program_text, packages=all_packages)
