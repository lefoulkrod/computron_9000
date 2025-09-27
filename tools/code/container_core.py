"""Container core functions for code execution tools (Python, Node.js).

Provides container management, code upload, and package installation utilities
used by the code execution tools in this project.
"""

import io
import logging
import tarfile

from podman import PodmanClient
from podman.domain.containers import Container

logger = logging.getLogger(__name__)

# Expected tuple length when demux=True: (stdout, stderr)
EXPECTED_OUTPUT_LEN = 2


class CodeExecutionError(Exception):
    """Custom exception for code execution errors."""


def _create_and_start_container(image: str) -> Container:
    """Create and start a Podman container with the specified image.

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
        logger.exception("Failed to create/start container")
        msg = f"Failed to create/start container: {e}"
        raise CodeExecutionError(msg) from e


def _upload_code_to_container(ctr: Container, filename: str, program_text: str) -> None:
    """Upload the code file to the container.

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
        msg = "Failed to upload script"
        raise CodeExecutionError(msg)


def _install_packages(ctr: Container, language: str, packages: list[str]) -> None:
    """Install packages in the running container.

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
        install_cmd = ["pip", "install", *packages]
    elif language == "node":
        install_cmd = ["npm", "--prefix", "/root", "install", *packages]
    else:
        msg = f"Unsupported language for package install: {language}"
        raise CodeExecutionError(msg)
    exit_code, output = ctr.exec_run(install_cmd, stdout=True, stderr=True, demux=True)
    logger.debug("Package install output: %s Exit code: %s", output, exit_code)
    if exit_code != 0:
        stderr = output[1].decode().strip() if output and isinstance(output, tuple) and output[1] else ""
        msg = f"Package installation failed: {stderr}"
        raise CodeExecutionError(msg)


def _parse_container_output(exit_code: int, output: object) -> dict[str, str | None]:
    """Parse the output from a container exec_run call.

    Args:
        exit_code (int): The exit code from the command.
        output: The output from exec_run (tuple or bytes).

    Returns:
        dict[str, str | None]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

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
) -> dict[str, str | None]:
    """Run code in a container, handling package install, upload, execution, and cleanup.

    Args:
        image (str): Container image.
        filename (str): Name of the code file in the container.
        command (list[str]): Command to execute.
        program_text (str): The code to run.
        language (str): Language for package install ('python' or 'node').
        packages (list[str] | None): Packages to install.

    Returns:
        dict[str, str | None]: Dictionary with 'stdout', 'stderr', and 'exit_code'.

    Raises:
        CodeExecutionError: On any failure.

    """
    ctr = None
    packages = packages or []
    logger.debug(
        "Running code in container: image=%s, filename=%s, language=%s, packages=%s",
        image,
        filename,
        language,
        packages,
    )
    try:
        ctr = _create_and_start_container(image)
        _install_packages(ctr, language, packages)
        _upload_code_to_container(ctr, filename, program_text)
        exit_code, output = ctr.exec_run(command, stdout=True, stderr=True, demux=True)
        exit_code = exit_code if exit_code is not None else -1
        result = _parse_container_output(exit_code, output)
        logger.debug("Execution completed: %s", result)
    except Exception as e:
        logger.exception("Execution in container failed")
        msg = f"Execution in container failed: {e}"
        raise CodeExecutionError(msg) from e
    else:
        return result
    finally:
        if ctr is not None:
            try:
                ctr.stop()
                ctr.remove()
            except Exception:
                logger.exception("Failed to cleanup container")
