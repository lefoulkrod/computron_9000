"""
Module for executing basic Python or Node.js programs in isolated containers using Podman.

This tool provides a function to execute code snippets in either Python or Node.js environments using Podman containers. It supports capturing stdout, stderr, and exit codes. Containers are stopped after execution but not removed.
"""

import logging
from typing import Dict, Optional

from tools.code.shared_code import (
    CodeExecutionError,
    _create_and_start_container,
    _install_packages,
    _upload_code_to_container,
)

logger = logging.getLogger(__name__)

def execute_program(program_text: str, language: str) -> Dict[str, Optional[str]]:
    """
    Execute a program in a containerized Python 3.12 or Node.js 20 environment.

    Only default (standard library) packages are supported. Custom or third-party packages are not available in the execution environment.

    Args:
        program_text (str): The program to execute.
        language (str): The language to use ('python' or 'node').

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution fails or language is unsupported.
    """
    if language not in ("python", "node"):
        logger.error(f"Unsupported language: {language}")
        raise CodeExecutionError(f"Unsupported language: {language}")

    logger.debug(f"Executing program in language: {language}\n--- Program Start ---\n{program_text}\n--- Program End ---")

    image = "python:3.12-slim" if language == "python" else "node:20-slim"
    filename = "main.py" if language == "python" else "main.js"
    command = ["python", f"/root/{filename}"] if language == "python" else ["node", f"/root/{filename}"]

    try:
        ctr = _create_and_start_container(image)
        _upload_code_to_container(ctr, filename, program_text)
        exit_code, output = ctr.exec_run(command, stdout=True, stderr=True, demux=True)
        stdout = None
        stderr = None

        if isinstance(output, tuple) and len(output) == 2:
            # output is (stdout, stderr)
            stdout = output[0].decode().strip() if output[0] else None
            stderr = output[1].decode().strip() if output[1] else None
        elif isinstance(output, bytes):
            stdout = output.decode().strip() if output else None

        ctr.stop()
        ctr.remove()

        logger.debug(f"Execution completed with exit code: {exit_code}, stdout: {stdout}, stderr: {stderr}")

        return {"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code) if exit_code is not None else None}
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise CodeExecutionError(f"Execution failed: {e}")

def execute_program_with_packages(program_text: str, language: str, packages: list[str]) -> Dict[str, Optional[str]]:
    """
    Execute a program in a containerized Python 3.12 or Node.js 20 environment, installing specified packages first.

    Args:
        program_text (str): The program to execute.
        language (str): The language to use ('python' or 'node').
        packages (list[str]): List of packages to install before execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails, or language is unsupported.
    """
    if language not in ("python", "node"):
        logger.error(f"Unsupported language: {language}")
        raise CodeExecutionError(f"Unsupported language: {language}")
    logger.debug(f"Executing program with packages in language: {language}\nPackages: {packages}\n--- Program Start ---\n{program_text}\n--- Program End ---")
    image = "python:3.12-slim" if language == "python" else "node:20-slim"
    filename = "main.py" if language == "python" else "main.js"
    command = ["python", f"/root/{filename}"] if language == "python" else ["node", f"/root/{filename}"]
    ctr = None
    try:
        ctr = _create_and_start_container(image)
        _install_packages(ctr, language, packages)
        _upload_code_to_container(ctr, filename, program_text)
        exit_code, output = ctr.exec_run(command, stdout=True, stderr=True, demux=True)
        stdout = None
        stderr = None
        if isinstance(output, tuple) and len(output) == 2:
            stdout = output[0].decode().strip() if output[0] else None
            stderr = output[1].decode().strip() if output[1] else None
        elif isinstance(output, bytes):
            stdout = output.decode().strip() if output else None
        logger.debug(f"Execution with packages completed with exit code: {exit_code}, stdout: {stdout}, stderr: {stderr}")
        return {"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code) if exit_code is not None else None}
    except Exception as e:
        logger.error(f"Execution with packages failed: {e}")
        raise CodeExecutionError(f"Execution with packages failed: {e}")
    finally:
        if ctr is not None:
            try:
                ctr.stop()
                ctr.remove()
            except Exception as cleanup_err:
                logger.error(f"Failed to cleanup container: {cleanup_err}")
