"""
Module for executing basic Python or Node.js programs in isolated containers using Podman.

This tool provides a function to execute code snippets in either Python or Node.js environments using Podman containers. It supports capturing stdout, stderr, and exit codes. Containers are stopped after execution but not removed.
"""

import io
import logging
import tarfile
from typing import Dict, Optional

from podman import PodmanClient
from podman.domain.containers import Container

logger = logging.getLogger(__name__)

class CodeExecutionError(Exception):
    """
    Custom exception for code execution errors.
    """
    pass

def _create_and_start_container(client: PodmanClient, image: str) -> Container:
    """
    Create and start a Podman container with the specified image.

    Args:
        client (PodmanClient): The Podman client instance.
        image (str): The image to use for the container.

    Returns:
        Container: The started container object.

    Raises:
        CodeExecutionError: If the container cannot be created or started.
    """
    try:
        client.images.pull(image)
        ctr = client.containers.create(image, command=["sleep", "infinity"])
        ctr.start()
        return ctr
    except Exception as e:
        logger.error(f"Failed to create/start container: {e}")
        raise CodeExecutionError(f"Failed to create/start container: {e}")

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
        packages (list[str]): List of packages to install.

    Raises:
        CodeExecutionError: If installation fails.
    """
    if not packages:
        return
    if language == "python":
        install_cmd = ["pip", "install"] + packages
    elif language == "node":
        install_cmd = ["npm", "install", "-g"] + packages
    else:
        raise CodeExecutionError(f"Unsupported language for package install: {language}")
    exit_code, output = ctr.exec_run(install_cmd, stdout=True, stderr=True, demux=True)
    if exit_code != 0:
        stderr = output[1].decode().strip() if output and isinstance(output, tuple) and output[1] else ""
        raise CodeExecutionError(f"Package installation failed: {stderr}")

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
        with PodmanClient.from_env() as client:
            ctr = _create_and_start_container(client, image)
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
    try:
        with PodmanClient.from_env() as client:
            ctr = _create_and_start_container(client, image)
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
            ctr.stop()
            return {"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code) if exit_code is not None else None}
    except Exception as e:
        logger.error(f"Execution with packages failed: {e}")
        raise CodeExecutionError(f"Execution with packages failed: {e}")
