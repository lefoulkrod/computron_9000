"""Tool for running bash commands in a container."""

import asyncio
import logging
from typing import TYPE_CHECKING

from podman import PodmanClient
from podman.domain.containers import Container
from pydantic import BaseModel

from config import load_config

if TYPE_CHECKING:
    from podman.domain.containers import Container

logger = logging.getLogger(__name__)


class RunBashCmdError(Exception):
    """Custom exception for errors during bash command execution in container.

    Args:
        message (str): Error message describing the failure.
    """

    def __init__(self, message: str) -> None:
        """Initialize RunBashCmdError.

        Args:
            message (str): Error message describing the failure.
        """
        super().__init__(message)


class BashCmdResult(BaseModel):
    """Validated result for a bash command executed in a container.

    Attributes:
        stdout (str | None): Standard output from the command.
        stderr (str | None): Standard error from the command.
        exit_code (int | None): Exit code from the command execution.
    """

    stdout: str | None
    stderr: str | None
    exit_code: int | None


BASH_CMD_TIMEOUT: float = 60.0


async def run_bash_cmd(cmd: str) -> BashCmdResult:
    """Execute a bash command in your virtual computer which is Ubuntu LTS.

    Execute any bash command with full access to a virtual computer. Times out after 60 seconds.

    Args:
        cmd (str): The bash command to execute.

    Returns:
        BashCmdResult: Validated result object containing stdout, stderr, and exit_code.

    Raises:
        RunBashCmdError: If execution fails, container is not found, or timeout occurs.
    """

    def _raise_container_not_found(container_name: str) -> None:
        msg = f"Container '{container_name}' not found."
        logger.error(msg)
        raise RunBashCmdError(msg)

    try:
        config = load_config()
        container_name = config.virtual_computer.container_name
        container_user = config.virtual_computer.container_user
        client = PodmanClient().from_env()
        containers = client.containers.list()
        container: Container | None = next(
            (c for c in containers if c.name == container_name), None
        )
        if container is None:
            _raise_container_not_found(container_name)
            return BashCmdResult(stdout=None, stderr=None, exit_code=None)

        exec_args = ["bash", "-c", cmd]

        loop = asyncio.get_running_loop()

        def _exec_run_sync() -> tuple[int | None, object]:
            return container.exec_run(
                exec_args,
                stdout=True,
                stderr=True,
                demux=True,
                tty=False,
                user=container_user,
            )

        try:
            exec_result = await asyncio.wait_for(
                loop.run_in_executor(None, _exec_run_sync), timeout=BASH_CMD_TIMEOUT
            )
        except TimeoutError:
            logger.exception(
                "Timeout after %s seconds running bash command: %s", BASH_CMD_TIMEOUT, cmd
            )
            msg = f"Timeout after {BASH_CMD_TIMEOUT} seconds running bash command: {cmd}"
            raise RunBashCmdError(msg) from None

        logger.debug("exec_result: %r", exec_result)

        # Parse the tuple return value
        exit_code, output = exec_result
        logger.debug("exit_code: %r", exit_code)

        stdout = None
        stderr = None
        output_tuple_len: int = 2
        if isinstance(output, tuple) and len(output) == output_tuple_len:
            stdout_bytes, stderr_bytes = output
            if stdout_bytes:
                stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            if stderr_bytes:
                stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            logger.debug("output tuple: %r", output)
        else:
            logger.warning("Unexpected output format: %r", output)

        logger.debug("parsed stdout: %r", stdout)
        logger.debug("parsed stderr: %r", stderr)

        return BashCmdResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code if exit_code is not None else None,
        )
    except Exception as exc:
        logger.exception("Failed to execute bash command '%s' in container.", cmd)
        msg = f"Execution failed: {exc}"
        raise RunBashCmdError(msg) from exc
