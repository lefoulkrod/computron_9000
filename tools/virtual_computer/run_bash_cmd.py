"""Tool for running bash commands in a container with guardrails.

Adds deny patterns, per-command timeouts, and strict bash flags to ensure only
short-lived, test-oriented commands execute in the headless execution environment.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from podman import PodmanClient
from podman.domain.containers import Container
from pydantic import BaseModel

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


BASH_CMD_TIMEOUT: float = 60.0

# Allowed top-level commands or command prefixes (conservative default)
_ALLOWED_PREFIXES: tuple[str, ...] = (
    "python",
    "python3",
    "pip",
    "pytest",
    "ruff",
    "mypy",
    "node",
    "npm",
    "git",
    "echo",
    "ls",
    "cat",
    "pwd",
)

# Deny substrings indicating long-running servers/watchers
_DENY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bserve\b", re.IGNORECASE),
    # Block explicit 'dev' scripts like `npm run dev` but allow flags like '--save-dev'.
    # Negative lookbehind ensures 'dev' isn't preceded by 'save-' (e.g. --save-dev)
    # or part of 'saved'.
    re.compile(r"(?<!save-)\bdev\b", re.IGNORECASE),
    re.compile(r"\bstart\b", re.IGNORECASE),
    re.compile(r"\bwatch\b", re.IGNORECASE),
    re.compile(r"tail\s+-f"),
    re.compile(r"sleep\s+inf(inity)?", re.IGNORECASE),
    re.compile(r"python\s+-m\s+http\.server"),
    re.compile(r"playwright\b.*\bheaded\b", re.IGNORECASE),
)


def _is_allowed_command(cmd: str) -> bool:
    """Check if a command is permitted by execution policy.

    Conservative rule: block only when a deny pattern matches; otherwise allow.
    This avoids breaking legitimate multi-line or compound shell commands used
    in tests.

    Args:
        cmd: The command string to evaluate.

    Returns:
        bool: True if allowed; False if a deny pattern matches or empty input.
    """
    lowered = cmd.strip()
    if not lowered:
        return False
    return all(not pat.search(lowered) for pat in _DENY_PATTERNS)


def _timeout_for(cmd: str) -> float:
    """Compute a timeout based on the command content.

    Args:
        cmd: The command string to evaluate.

    Returns:
        float: Timeout in seconds. Uses command-specific overrides for common
        long-running operations; otherwise defaults to ``BASH_CMD_TIMEOUT``.
    """
    text = cmd.strip()
    if "pip install" in text or "-m venv" in text:
        return 180.0
    if text.startswith("pytest"):
        return 120.0
    return BASH_CMD_TIMEOUT


async def run_bash_cmd(cmd: str) -> BashCmdResult:
    """Execute a bash command in the virtual computer.

    Enforces deny patterns, strict bash flags, and per-command timeouts.

    Args:
        cmd: The bash command to execute.

    Returns:
        BashCmdResult: Object containing ``stdout``, ``stderr``, and ``exit_code``.

    Raises:
        RunBashCmdError: If execution fails or a timeout occurs.
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

        # Enforce execution policy (deny patterns)
        if not _is_allowed_command(cmd):
            msg = "Command is not allowed by execution policy"
            logger.error("%s: %s", msg, cmd)
            return BashCmdResult(stdout=None, stderr=msg, exit_code=126)

        # Add strict flags to ensure one-shot behavior
        strict_cmd = f"set -euo pipefail; {cmd}"
        exec_args = ["bash", "-c", strict_cmd]

        workspace_folder = get_current_workspace_folder()
        container_working_dir = config.virtual_computer.container_working_dir.rstrip("/")
        workdir = (
            f"{container_working_dir}/{workspace_folder}"
            if workspace_folder
            else container_working_dir
        )

        loop = asyncio.get_running_loop()

        def _exec_run_sync() -> tuple[int | None, object]:
            exec_run_kwargs = {
                "stdout": True,
                "stderr": True,
                "demux": True,
                "tty": False,
                "user": container_user,
                "workdir": workdir,
            }
            return container.exec_run(exec_args, **exec_run_kwargs)

        try:
            exec_result = await asyncio.wait_for(
                loop.run_in_executor(None, _exec_run_sync), timeout=_timeout_for(cmd)
            )
        except TimeoutError:
            timeout_used = _timeout_for(cmd)
            logger.exception("Timeout after %s seconds running bash command: %s", timeout_used, cmd)
            msg = f"Timeout after {timeout_used} seconds running bash command: {cmd}"
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
