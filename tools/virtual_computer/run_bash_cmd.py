"""Tool for running bash commands locally with guardrails.

Adds deny patterns, per-command timeouts, and strict bash flags.
Commands execute as the ``computron`` user via ``sudo -u computron``.
"""

import asyncio
import logging
import shlex
import uuid

from pydantic import BaseModel

from config import load_config
from sdk.events import AgentEvent, TerminalOutputPayload, publish_event
from tools._truncation import truncate_args
from tools.virtual_computer._policy import is_allowed_command as _is_allowed_command

logger = logging.getLogger(__name__)


class RunBashCmdError(Exception):
    """Error raised when a bash command execution fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BashCmdResult(BaseModel):
    """Result for a bash command execution."""

    stdout: str | None
    stderr: str | None
    exit_code: int | None


BASH_CMD_TIMEOUT: float = 600.0


@truncate_args(cmd=500)
async def run_bash_cmd(cmd: str, timeout: float = BASH_CMD_TIMEOUT) -> BashCmdResult:
    """Execute a bash command locally.

    Runs one-shot commands under ``set -euo pipefail``.

    For long-running processes, background them with ``&`` and redirect output::

        run_bash_cmd("python game.py > /tmp/game.log 2>&1 &")

    Args:
        cmd: The bash command to execute.
        timeout: Max seconds to wait. Default 600.

    Returns:
        BashCmdResult: ``stdout``, ``stderr``, and ``exit_code``.
    """
    try:
        # Enforce execution policy (deny patterns) before running.
        if not _is_allowed_command(cmd):
            msg = "Command is not allowed by execution policy"
            logger.error("%s: %s", msg, cmd)
            return BashCmdResult(stdout=None, stderr=msg, exit_code=126)

        config = load_config()
        workdir = config.virtual_computer.home_dir

        strict_cmd = "set -euo pipefail; %s" % cmd

        # Publish a "running" event so the UI shows the command immediately.
        cmd_id = uuid.uuid4().hex
        publish_event(AgentEvent(payload=TerminalOutputPayload(
            type="terminal_output",
            cmd_id=cmd_id,
            cmd=cmd,
            status="running",
        )))

        # Run as the unprivileged computron user. The app server runs as
        # computron_app and uses sudo to drop to computron for agent commands.
        agent_cmd = "sudo -n -u computron bash -c %s" % shlex.quote(strict_cmd)

        proc = await asyncio.create_subprocess_shell(
            agent_cmd,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def _read_stream(
            stream: asyncio.StreamReader | None,
            parts: list[str],
            is_stderr: bool,
        ) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                parts.append(text)
                publish_event(AgentEvent(payload=TerminalOutputPayload(
                    type="terminal_output",
                    cmd_id=cmd_id,
                    cmd=cmd,
                    status="streaming",
                    stdout=None if is_stderr else text,
                    stderr=text if is_stderr else None,
                )))

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    _read_stream(proc.stdout, stdout_parts, is_stderr=False),
                    _read_stream(proc.stderr, stderr_parts, is_stderr=True),
                ),
                timeout=timeout,
            )
            await proc.wait()
        except TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("Timeout after %s seconds running bash command: %s", timeout, cmd)
            msg = "Timeout after %s seconds running bash command: %s" % (timeout, cmd)
            raise RunBashCmdError(msg) from None

        exit_code = proc.returncode
        stdout = "".join(stdout_parts).strip() or None
        stderr = "".join(stderr_parts).strip() or None

        # Publish the completed event with final output and exit code.
        publish_event(AgentEvent(payload=TerminalOutputPayload(
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
            exit_code=exit_code,
        )
    except RunBashCmdError:
        raise
    except Exception as exc:
        logger.exception("Failed to execute bash command: %s", cmd)
        msg = "Execution failed: %s" % exc
        raise RunBashCmdError(msg) from exc
