"""Tool for running bash commands in a container with guardrails.

Adds deny patterns, per-command timeouts, and strict bash flags to ensure only
short-lived, test-oriented commands execute in the headless execution environment.
"""

import asyncio
import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

from podman import PodmanClient
from podman.api import stream_frames
from podman.domain.containers import Container
from pydantic import BaseModel

from sdk.events import AgentEvent, TerminalOutputPayload, publish_event
from tools._truncation import truncate_args
from config import load_config
from tools.virtual_computer.workspace import get_current_workspace_folder

if TYPE_CHECKING:
    from podman.domain.containers import Container

logger = logging.getLogger(__name__)


class RunBashCmdError(Exception):
    """Error raised when a bash command execution fails in the container.

    Args:
        message: Error message describing the failure.
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
    stdout: Standard output from the command.
    stderr: Standard error from the command.
    exit_code: Exit code from the command execution.
    """

    stdout: str | None
    stderr: str | None
    exit_code: int | None


BASH_CMD_TIMEOUT: float = 600.0

# Re-export for internal use within this module.
from tools.virtual_computer._policy import is_allowed_command as _is_allowed_command


@truncate_args(cmd=500)
async def run_bash_cmd(cmd: str, timeout: float = BASH_CMD_TIMEOUT) -> BashCmdResult:
    """Execute a bash command in the virtual computer container.

    Runs one-shot commands under ``set -euo pipefail``. Package installs
    (pip, npm, apt) are auto-promoted to root. Dev servers, watch mode, and
    other long-running/blocking processes are blocked (exit code 126).

    Args:
        cmd: The bash command to execute.
        timeout: Max seconds to wait. Default 600.

    Returns:
        BashCmdResult: ``stdout``, ``stderr``, and ``exit_code``.
    """

    def _raise_container_not_found(container_name: str) -> None:
        msg = f"Container '{container_name}' not found."
        logger.error(msg)
        raise RunBashCmdError(msg)

    try:
        # Enforce execution policy (deny patterns) BEFORE any container operations.
        # This ensures clearly-blocked commands fail fast with exit code 126 and do
        # not depend on a running container for test environments.
        if not _is_allowed_command(cmd):
            msg = "Command is not allowed by execution policy"
            logger.error("%s: %s", msg, cmd)
            return BashCmdResult(stdout=None, stderr=msg, exit_code=126)

        config = load_config()
        container_name = config.virtual_computer.container_name
        container_user = config.virtual_computer.container_user
        client = PodmanClient().from_env()
        containers = client.containers.list()
        container: Container | None = next((c for c in containers if c.name == container_name), None)
        if container is None:
            _raise_container_not_found(container_name)
            return BashCmdResult(stdout=None, stderr=None, exit_code=None)

        # Add strict flags to ensure one-shot behavior
        strict_cmd = f"set -euo pipefail; {cmd}"
        exec_args = ["bash", "-c", strict_cmd]

        workspace_folder = get_current_workspace_folder()
        container_working_dir = config.virtual_computer.container_working_dir.rstrip("/")
        workdir = f"{container_working_dir}/{workspace_folder}" if workspace_folder else container_working_dir

        loop = asyncio.get_running_loop()

        # Package installs need root to write to system site-packages.
        # Promote pip/pip3/npm/apt-get/apt install commands to root automatically.
        _is_pkg_install = re.search(
            r"\bpip3?\s+install\b|\bnpm\s+install\b|\bapt(?:-get)?\s+install\b",
            cmd,
        )
        exec_user = "root" if _is_pkg_install else container_user

        # Publish a "running" event so the UI shows the command immediately.
        cmd_id = uuid.uuid4().hex
        publish_event(AgentEvent(event=TerminalOutputPayload(
            type="terminal_output",
            cmd_id=cmd_id,
            cmd=cmd,
            status="running",
        )))

        # Use the lower-level Podman API to stream output in real time.
        # 1. Create exec instance  2. Start with stream=True
        # 3. Read frames and publish chunks  4. Inspect exec for exit code
        api_client = client.api

        exec_data = {
            "AttachStderr": True,
            "AttachStdout": True,
            "AttachStdin": False,
            "Cmd": exec_args,
            "Tty": False,
            "User": exec_user,
            "WorkingDir": workdir,
        }

        create_resp = api_client.post(
            f"/containers/{container.name}/exec",
            data=json.dumps(exec_data),
        )
        create_resp.raise_for_status()
        exec_id = create_resp.json()["Id"]

        # Bridge sync streaming iterator -> async via queue in a thread
        queue: asyncio.Queue[tuple[bytes | None, bytes | None] | None] = asyncio.Queue()

        def _stream_sync() -> None:
            """Run in a thread: start exec, read frames, push to queue."""
            start_resp = api_client.post(
                f"/exec/{exec_id}/start",
                data=json.dumps({"Detach": False, "Tty": False}),
                stream=True,
            )
            start_resp.raise_for_status()
            # APIResponse proxies attribute access to the underlying
            # requests.Response, so stream_frames works at runtime.
            for frame in stream_frames(start_resp, demux=True):  # type: ignore[arg-type]
                loop.call_soon_threadsafe(queue.put_nowait, frame)  # type: ignore[arg-type]
            # Sentinel to signal stream ended
            loop.call_soon_threadsafe(queue.put_nowait, None)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        try:
            stream_task = loop.run_in_executor(None, _stream_sync)

            async def _consume_stream() -> None:
                while True:
                    frame = await queue.get()
                    if frame is None:
                        break
                    stdout_chunk, stderr_chunk = frame
                    chunk_out = None
                    chunk_err = None
                    if stdout_chunk:
                        chunk_out = stdout_chunk.decode("utf-8", errors="replace")
                        stdout_parts.append(chunk_out)
                    if stderr_chunk:
                        chunk_err = stderr_chunk.decode("utf-8", errors="replace")
                        stderr_parts.append(chunk_err)
                    if chunk_out or chunk_err:
                        publish_event(AgentEvent(event=TerminalOutputPayload(
                            type="terminal_output",
                            cmd_id=cmd_id,
                            cmd=cmd,
                            status="streaming",
                            stdout=chunk_out,
                            stderr=chunk_err,
                        )))

            await asyncio.wait_for(
                asyncio.gather(stream_task, _consume_stream()),
                timeout=timeout,
            )
        except TimeoutError:
            logger.exception("Timeout after %s seconds running bash command: %s", timeout, cmd)
            msg = f"Timeout after {timeout} seconds running bash command: {cmd}"
            raise RunBashCmdError(msg) from None

        # Retrieve exit code from the completed exec instance
        inspect_resp = api_client.get(f"/exec/{exec_id}/json")
        inspect_resp.raise_for_status()
        exit_code = inspect_resp.json().get("ExitCode")

        stdout = "".join(stdout_parts).strip() or None
        stderr = "".join(stderr_parts).strip() or None

        logger.debug("parsed stdout: %r", stdout)
        logger.debug("parsed stderr: %r", stderr)

        # Publish the completed event with final output and exit code.
        publish_event(AgentEvent(event=TerminalOutputPayload(
            type="terminal_output",
            cmd_id=cmd_id,
            cmd=cmd,
            status="completed",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )))

        return BashCmdResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code if exit_code is not None else None,
        )
    except Exception as exc:
        logger.exception("Failed to execute bash command '%s' in container.", cmd)
        msg = f"Execution failed: {exc}"
        raise RunBashCmdError(msg) from exc
