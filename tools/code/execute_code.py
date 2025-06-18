"""
Module for executing basic Python or Node.js programs in isolated containers using Podman.

This tool provides a function to execute code snippets in either Python or Node.js environments using Podman containers. It supports capturing stdout, stderr, and exit codes. Containers are stopped after execution but not removed.
"""

import io
import logging
import tarfile
from typing import Dict, Optional

from podman import PodmanClient

logger = logging.getLogger(__name__)

class CodeExecutionError(Exception):
    """
    Custom exception for code execution errors.
    """
    pass

def execute_program(program_text: str, language: str) -> Dict[str, Optional[str]]:
    """
    Execute a program in a containerized Python 3.12 or Node.js 20 environment.

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

    image = "python:3.12-slim" if language == "python" else "node:20-slim"
    filename = "main.py" if language == "python" else "main.js"
    command = ["python", f"/root/{filename}"] if language == "python" else ["node", f"/root/{filename}"]

    try:
        with PodmanClient.from_env() as client:
            client.images.pull(image)
            ctr = client.containers.create(image, command=["sleep", "infinity"])
            ctr.start()

            # Build a tar archive in memory containing the code file
            buf = io.BytesIO()
            code_bytes = program_text.encode()
            with tarfile.open(fileobj=buf, mode="w") as tf:
                info = tarfile.TarInfo(filename)
                info.size = len(code_bytes)
                tf.addfile(info, io.BytesIO(code_bytes))
            buf.seek(0)

            # Upload to /root inside container
            success = ctr.put_archive("/root", buf.getvalue())
            if not success:
                raise CodeExecutionError("Failed to upload script")

            # Execute the script
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
            # Do not remove the container as per requirements

            return {"stdout": stdout, "stderr": stderr, "exit_code": str(exit_code) if exit_code is not None else None}
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise CodeExecutionError(f"Execution failed: {e}")
