"""Low-level subprocess execution helper for desktop commands."""

import asyncio
import logging
import shlex
from contextvars import ContextVar

from config import load_config

logger = logging.getLogger(__name__)

# ContextVar for per-agent display routing.  When set, desktop tools
# operate on this display instead of the default user display.
_current_display: ContextVar[str | None] = ContextVar("_current_display", default=None)


class DesktopExecError(Exception):
    """Raised when a desktop command fails."""


_DEFAULT_TIMEOUT_S = 30.0


async def _run_desktop_cmd(
    cmd: str,
    *,
    display: str | None = None,
    user: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> str:
    """Run a command locally with DISPLAY set.

    Args:
        cmd: Shell command to execute.
        display: X11 display to use.  If ``None``, reads from the
            ``_current_display`` ContextVar, falling back to the user
            display from config.
        user: Run as this user. "root" uses sudo.
        timeout: Max seconds to wait for the command.

    Returns:
        Combined stdout/stderr output.

    Raises:
        DesktopExecError: If the command fails or times out.
    """
    config = load_config()
    if display is None:
        display = _current_display.get() or config.desktop.user_display

    inner_cmd = "export DISPLAY=%s; %s" % (display, cmd)
    if user == "root":
        shell_cmd = "sudo -n bash -c %s" % shlex.quote(inner_cmd)
    else:
        # Run as the computron desktop user.  The app server process
        # (computron_app) drops to computron via sudo.
        shell_cmd = "sudo -n -u computron bash -c %s" % shlex.quote(inner_cmd)

    try:
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except TimeoutError:
        logger.error("Desktop command timed out after %ss: %s", timeout, cmd)
        raise DesktopExecError(
            "Desktop command timed out after %ss: %s" % (timeout, cmd),
        )
    except Exception as exc:
        logger.exception("Desktop command failed: %s", cmd)
        raise DesktopExecError("Desktop command failed: %s" % exc) from exc

    output = (stdout or b"").decode("utf-8", errors="replace")
    if stderr:
        output += (stderr).decode("utf-8", errors="replace")

    if proc.returncode != 0:
        logger.warning(
            "Desktop command exited %d: %s — output: %s",
            proc.returncode, cmd, output.strip(),
        )

    return output
