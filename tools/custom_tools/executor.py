"""Container execution of custom tools via Podman."""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from typing import TYPE_CHECKING

from podman import PodmanClient

from config import load_config

from .registry import CustomToolDefinition

if TYPE_CHECKING:
    from podman.domain.containers import Container

logger = logging.getLogger(__name__)

# Process-lifetime cache: packages already installed in this container session.
_installed_packages: set[str] = set()

_DEFAULT_TIMEOUT: float = 300.0
_INSTALL_TIMEOUT: float = 180.0


def _get_container() -> tuple[Container, str]:
    """Return (container, container_user), raising RuntimeError if not found."""
    cfg = load_config()
    container_name = cfg.virtual_computer.container_name
    container_user = cfg.virtual_computer.container_user
    client = PodmanClient().from_env()
    container = next(
        (c for c in client.containers.list() if c.name == container_name),
        None,
    )
    if container is None:
        msg = f"Container '{container_name}' not found."
        raise RuntimeError(msg)
    return container, container_user


def _exec_sync(
    container: Container,
    cmd: list[str],
    user: str,
    timeout: float,
) -> dict[str, object]:
    """Run cmd in container synchronously and return stdout/stderr/exit_code."""
    exit_code, output = container.exec_run(
        cmd,
        stdout=True,
        stderr=True,
        demux=True,
        tty=False,
        user=user,
    )
    stdout = None
    stderr = None
    if isinstance(output, tuple) and len(output) == 2:
        stdout_bytes, stderr_bytes = output
        if stdout_bytes:
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        if stderr_bytes:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


async def _ensure_dependencies(
    container: Container,
    container_user: str,
    dependencies: list[str],
    language: str,
) -> None:
    """Install missing dependencies in the container (cached per process lifetime)."""
    missing = [pkg for pkg in dependencies if pkg not in _installed_packages]
    if not missing:
        return

    if language == "python":
        # Run as root so we can write to the system site-packages.
        cmd = ["pip3", "install", *missing]
        install_user = "root"
    else:
        cmd = ["npm", "install", "-g", *missing]
        install_user = "root"

    logger.info("Installing dependencies in container as root: %s", missing)
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _exec_sync(container, cmd, install_user, _INSTALL_TIMEOUT)),
            timeout=_INSTALL_TIMEOUT,
        )
    except TimeoutError:
        logger.warning("Dependency install timed out after %s seconds", _INSTALL_TIMEOUT)
        return

    _installed_packages.update(missing)


async def execute_custom_tool(tool_def: CustomToolDefinition, arguments: dict[str, object]) -> dict[str, object]:
    """Execute a custom tool inside the container.

    Args:
        tool_def: The tool definition from the registry.
        arguments: Dict of argument name → value.

    Returns:
        dict with stdout, stderr, exit_code.
    """
    container, container_user = _get_container()

    if tool_def.dependencies:
        await _ensure_dependencies(container, container_user, tool_def.dependencies, tool_def.language)

    loop = asyncio.get_running_loop()

    if tool_def.type == "command":
        # Interpolate {param} placeholders with shell-quoted argument values.
        cmd_str = tool_def.command_template
        for key, value in arguments.items():
            cmd_str = cmd_str.replace(f"{{{key}}}", shlex.quote(str(value)))
        exec_cmd = ["bash", "-c", cmd_str]

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _exec_sync(container, exec_cmd, container_user, _DEFAULT_TIMEOUT)),
                timeout=_DEFAULT_TIMEOUT,
            )
        except TimeoutError:
            return {"stdout": None, "stderr": f"Timed out after {_DEFAULT_TIMEOUT}s", "exit_code": 1}

    else:
        # program type: pass arguments as JSON on stdin
        json_args = json.dumps(arguments)
        script_path = f"/home/computron/custom_tools/scripts/{tool_def.script_filename}"
        interpreter = "python3" if tool_def.language == "python" else "bash"
        cmd_str = f"echo {shlex.quote(json_args)} | {interpreter} {shlex.quote(script_path)}"
        exec_cmd = ["bash", "-c", cmd_str]

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _exec_sync(container, exec_cmd, container_user, _DEFAULT_TIMEOUT)),
                timeout=_DEFAULT_TIMEOUT,
            )
        except TimeoutError:
            return {"stdout": None, "stderr": f"Timed out after {_DEFAULT_TIMEOUT}s", "exit_code": 1}

    return result


__all__ = ["execute_custom_tool"]
