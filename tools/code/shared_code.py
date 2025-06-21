"""
Shared functions for code execution tools (Python, Node.js, Playwright) using Podman containers.

This module provides container management, code upload, and package installation utilities for use by code execution tools.
"""

import io
import logging
import tarfile
from typing import List

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

def _install_packages(ctr: Container, language: str, packages: List[str]) -> None:
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
        raise CodeExecutionError(f"Unsupported language for package install: {language}")
    exit_code, output = ctr.exec_run(install_cmd, stdout=True, stderr=True, demux=True)
    logger.debug(f"Package install output: {output} Exit code: {exit_code}")
    if exit_code != 0:
        stderr = output[1].decode().strip() if output and isinstance(output, tuple) and output[1] else ""
        raise CodeExecutionError(f"Package installation failed: {stderr}")
