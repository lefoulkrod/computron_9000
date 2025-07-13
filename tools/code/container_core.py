"""
Container core functions for code execution tools (Python, Node.js) using containers.

This module provides container management, code upload, and package installation utilities for use by code execution tools.
"""

import io
import logging
import tarfile
from typing import Any

from podman import PodmanClient
from podman.domain.containers import Container

logger = logging.getLogger(__name__)


class CodeExecutionError(Exception):
    """
    Custom exception for code execution errors.
    """

    pass


def _create_and_start_container(image: str) -> Container:
    """
    Create and start a Podman container with the specified image.

    Args:
        image (str): The image to use for the container.

    Returns:
        Container: The started container object.

    Raises:
        CodeExecutionError: If the container cannot be created or started.
    """
    try:
        with PodmanClient.from_env() as client:
            client.images.pull(image)
            ctr = client.containers.create(image, command=["sleep", "infinity"])
            ctr.start()
            return ctr
    except Exception as e:
        logger.error(f"Failed to create/start container: {e}")
        raise CodeExecutionError(f"Failed to create/start container: {e}") from e


def _upload_code_to_container(ctr: Container, filename: str, program_text: str) -> None:
    """
    Upload the code file to the container.

    Args:
        ctr (Container): The container object.
        filename (str): The filename to use inside the container.
        program_text (str): The code to upload.

    Raises:
        CodeExecutionError: If the upload fails.
    """
    buf = io.BytesIO()
    code_bytes = program_text.encode()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(filename)
        info.size = len(code_bytes)
        tf.addfile(info, io.BytesIO(code_bytes))
    buf.seek(0)
    success = ctr.put_archive("/root", buf.getvalue())
    if not success:
        raise CodeExecutionError("Failed to upload script")


def _install_packages(ctr: Container, language: str, packages: list[str]) -> None:
    """
    Install packages in the running container.

    Args:
        ctr (Container): The container object.
        language (str): The language ('python' or 'node').
        packages (List[str]): List of packages to install.

    Raises:
        CodeExecutionError: If installation fails.
    """
    if not packages:
        return
    if language == "python":
        install_cmd = ["pip", "install"] + packages
    elif language == "node":
        install_cmd = ["npm", "--prefix", "/root", "install"] + packages
    else:
        raise CodeExecutionError(
            f"Unsupported language for package install: {language}"
        )
    exit_code, output = ctr.exec_run(install_cmd, stdout=True, stderr=True, demux=True)
    logger.debug(f"Package install output: {output} Exit code: {exit_code}")
    if exit_code != 0:
        stderr = (
            output[1].decode().strip()
            if output and isinstance(output, tuple) and output[1]
            else ""
        )
        raise CodeExecutionError(f"Package installation failed: {stderr}")


def _parse_container_output(exit_code: int, output: Any) -> dict:
    """
    Parse the output from a container exec_run call.

    Args:
        exit_code (int): The exit code from the command.
        output: The output from exec_run (tuple or bytes).

    Returns:
        dict: Dictionary with 'stdout', 'stderr', and 'exit_code'.
    """
    stdout = None
    stderr = None
    if isinstance(output, tuple) and len(output) == 2:
        stdout = output[0].decode().strip() if output[0] else None
        stderr = output[1].decode().strip() if output[1] else None
    elif isinstance(output, bytes):
        stdout = output.decode().strip() if output else None
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": str(exit_code) if exit_code is not None else None,
    }


def _run_code_in_container(
    image: str,
    filename: str,
    command: list[str],
    program_text: str,
    language: str,
    packages: list[str] | None = None,
) -> dict:
    """
    Run code in a container, handling package install, upload, execution, and cleanup.

    Args:
        image (str): Container image.
        filename (str): Name of the code file in the container.
        command (list[str]): Command to execute.
        program_text (str): The code to run.
        language (str): Language for package install ('python' or 'node').
        packages (list[str] | None): Packages to install.

    Returns:
        dict: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: On any failure.
    """
    ctr = None
    packages = packages or []
    logger.debug(
        f"Running code in container: image={image}, filename={filename}, language={language}, packages={packages}\n--- Code Start ---\n{program_text}\n--- Code End ---"
    )
    try:
        ctr = _create_and_start_container(image)
        _install_packages(ctr, language, packages)
        _upload_code_to_container(ctr, filename, program_text)
        exit_code, output = ctr.exec_run(command, stdout=True, stderr=True, demux=True)
        exit_code = exit_code if exit_code is not None else -1
        result = _parse_container_output(exit_code, output)
        logger.debug(f"Execution completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Execution in container failed: {e}")
        raise CodeExecutionError(f"Execution in container failed: {e}") from e
    finally:
        if ctr is not None:
            try:
                ctr.stop()
                ctr.remove()
            except Exception as cleanup_err:
                logger.error(f"Failed to cleanup container: {cleanup_err}")
