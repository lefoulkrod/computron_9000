"""Low-level container execution helper for desktop commands."""

import asyncio
import logging

from podman import PodmanClient

from config import load_config

logger = logging.getLogger(__name__)


def _strip_stream_headers(data: bytes) -> bytes:
    """Strip Docker/Podman stream multiplexing headers from exec output.

    Stream framing uses 8-byte headers: [type(1)][pad(3)][size(4)] followed
    by *size* bytes of payload.  The type byte is 0 (stdin), 1 (stdout), or
    2 (stderr) and the three padding bytes are always zero.
    """
    if len(data) < 8 or data[0] not in (0, 1, 2) or data[1:4] != b"\x00\x00\x00":
        return data
    result = bytearray()
    pos = 0
    while pos + 8 <= len(data):
        if data[pos] not in (0, 1, 2) or data[pos + 1 : pos + 4] != b"\x00\x00\x00":
            # Not a valid framing header — append the rest verbatim.
            result.extend(data[pos:])
            break
        size = int.from_bytes(data[pos + 4 : pos + 8], "big")
        pos += 8
        end = min(pos + size, len(data))
        result.extend(data[pos:end])
        pos = end
    else:
        # Trailing bytes after last complete frame.
        if pos < len(data):
            result.extend(data[pos:])
    return bytes(result)


class DesktopExecError(Exception):
    """Raised when a desktop command fails in the container."""


async def _run_desktop_cmd(
    cmd: str,
    *,
    display: str = ":1",
    user: str | None = None,
) -> str:
    """Run a command in the container with DISPLAY set.

    Args:
        cmd: Shell command to execute.
        display: X11 display to use.
        user: Container user to run as. Defaults to config user.

    Returns:
        Combined stdout/stderr output.

    Raises:
        DesktopExecError: If the command fails or container is not found.
    """
    config = load_config()
    container_name = config.virtual_computer.container_name
    container_user = user or config.virtual_computer.container_user

    loop = asyncio.get_running_loop()

    def _exec_sync() -> tuple[int, str]:
        client = PodmanClient().from_env()
        containers = client.containers.list()
        container = next(
            (c for c in containers if c.name == container_name), None,
        )
        if container is None:
            msg = "Container '%s' not found"
            raise DesktopExecError(msg % container_name)

        exit_code, output = container.exec_run(
            ["bash", "-c", f"export DISPLAY={display}; {cmd}"],
            user=container_user,
        )
        clean = _strip_stream_headers(output) if output else b""
        decoded = clean.decode("utf-8", errors="replace")
        return exit_code, decoded

    try:
        exit_code, output = await loop.run_in_executor(None, _exec_sync)
    except DesktopExecError:
        raise
    except Exception as exc:
        logger.exception("Desktop command failed: %s", cmd)
        raise DesktopExecError("Desktop command failed: %s" % exc) from exc

    if exit_code != 0:
        logger.warning(
            "Desktop command exited %d: %s — output: %s",
            exit_code, cmd, output.strip(),
        )

    return output
