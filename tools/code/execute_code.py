"""Module for executing Python and Node.js programs in isolated containers.

Provides helpers to run code snippets inside containers while capturing
stdout, stderr, and exit codes. Containers are stopped and removed after use.
"""

import logging

from tools.code.container_core import (
    _run_code_in_container,
)

logger = logging.getLogger(__name__)


def execute_python_program(
    program_text: str,
    packages: list[str] | None = None,
) -> dict[str, str | None]:
    """Execute a Python program in a containerized Python 3.12 environment, installing specified packages first.

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


def execute_nodejs_program(
    program_text: str,
    packages: list[str] | None = None,
) -> dict[str, str | None]:
    """Execute a Node.js script in a containerized Node.js environment, installing specified packages first.

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


def execute_nodejs_program_with_playwright(
    program_text: str,
    packages: list[str] | None = None,
) -> dict[str, str | None]:
    """Execute a Node.js program in a container with Playwright & browsers installed.

    This helper is intended for web navigation tasks but can run arbitrary Node.js
    code (it's not limited to Playwright scripts).

    Args:
        program_text (str): The Node.js script to execute.
        packages (Optional[List[str]]): List of npm packages to install before
            execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and
            'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails.

    """
    packages = packages or []
    all_packages = list({*packages, "playwright@1.53.1"})
    return execute_nodejs_program(program_text=program_text, packages=all_packages)
