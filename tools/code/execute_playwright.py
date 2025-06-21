"""
Module for executing Playwright test scripts in isolated containers using Podman.

This tool provides a function to execute Playwright test scripts in a Node.js environment using Podman containers. It installs required npm packages (always including @playwright/test@latest), uploads the script, and runs it. Shared logic is imported from the shared_code module.
"""

import logging
from typing import Dict, List, Optional

from tools.code.shared_code import (
    CodeExecutionError,
    _create_and_start_container,
    _install_packages,
    _upload_code_to_container,
)

logger = logging.getLogger(__name__)

def execute_playwright_script(program_text: str, packages: List[str]) -> Dict[str, Optional[str]]:
    """
    Execute a Playwright script in a containerized Node.js environment, installing specified packages first.
    Playwright will always be installed as it is required for execution.

    Args:
        program_text (str): The Playwright test script to execute.
        packages (List[str]): List of npm packages to install before execution.

    Returns:
        Dict[str, Optional[str]]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: If execution or package installation fails.
    """
    image = "playwright:v1.53.1-noble"
    filename = "main.js"
    command = ["node", f"/root/{filename}"]
    all_packages = list(set(packages + ["playwright@1.53.1"]))
    logger.debug(f"Executing Playwright script with packages: {all_packages}\n--- Script Start ---\n{program_text}\n--- Script End ---")
    ctr = None
    try:
        ctr = _create_and_start_container(image)
        _install_packages(ctr, "node", all_packages)
        _upload_code_to_container(ctr, filename, program_text)
        exit_code, output = ctr.exec_run(command, stdout=True, stderr=True, demux=True)
        stdout = None
        stderr = None
        if isinstance(output, tuple) and len(output) == 2:
            stdout = output[0].decode().strip() if output[0] else None
            stderr = output[1].decode().strip() if output[1] else None
        elif isinstance(output, bytes):
            stdout = output.decode().strip() if output else None
        logger.debug(f"Playwright execution completed with exit code: {exit_code}, stdout: {stdout}, stderr: {stderr}")
        return {"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code) if exit_code is not None else None}
    except Exception as e:
        logger.error(f"Playwright execution failed: {e}")
        raise CodeExecutionError(f"Playwright execution failed: {e}")
    finally:
        if ctr is not None:
            try:
                ctr.stop()
                ctr.remove()
            except Exception as cleanup_err:
                logger.error(f"Failed to cleanup container: {cleanup_err}")
