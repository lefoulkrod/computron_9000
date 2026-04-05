"""Local execution of custom tools."""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import subprocess

from config import load_config

from .registry import CustomToolDefinition

logger = logging.getLogger(__name__)

# Process-lifetime cache: packages already installed in this session.
_installed_packages: set[str] = set()

_DEFAULT_TIMEOUT: float = 300.0
_INSTALL_TIMEOUT: float = 180.0


def _exec_sync(
    cmd: list[str],
    timeout: float,
    *,
    user: str | None = None,
) -> dict[str, object]:
    """Run cmd locally and return stdout/stderr/exit_code.

    Args:
        cmd: Command and arguments to run.
        timeout: Max seconds to wait.
        user: If set, run as this user via ``sudo -u``.
    """
    if user:
        cmd = ["sudo", "-n", "-u", user] + cmd
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
    )
    stdout = result.stdout.decode("utf-8", errors="replace").strip() if result.stdout else None
    stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else None
    return {"stdout": stdout, "stderr": stderr, "exit_code": result.returncode}


async def _ensure_dependencies(
    dependencies: list[str],
    language: str,
) -> None:
    """Install missing dependencies locally (cached per process lifetime)."""
    missing = [pkg for pkg in dependencies if pkg not in _installed_packages]
    if not missing:
        return

    if language == "python":
        cmd = ["pip3", "install", *missing]
    else:
        cmd = ["npm", "install", "-g", *missing]

    logger.info("Installing dependencies: %s", missing)
    loop = asyncio.get_running_loop()
    try:
        # Install as root so packages are available system-wide.
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _exec_sync(cmd, _INSTALL_TIMEOUT, user="root")),
            timeout=_INSTALL_TIMEOUT,
        )
    except TimeoutError:
        logger.warning("Dependency install timed out after %s seconds", _INSTALL_TIMEOUT)
        return

    _installed_packages.update(missing)


async def execute_custom_tool(tool_def: CustomToolDefinition, arguments: dict[str, object]) -> dict[str, object]:
    """Execute a custom tool locally.

    Args:
        tool_def: The tool definition from the registry.
        arguments: Dict of argument name -> value.

    Returns:
        dict with stdout, stderr, exit_code.
    """
    if tool_def.dependencies:
        await _ensure_dependencies(tool_def.dependencies, tool_def.language)

    loop = asyncio.get_running_loop()
    cfg = load_config()
    home_dir = cfg.virtual_computer.home_dir

    if tool_def.type == "command":
        cmd_str = tool_def.command_template
        for key, value in arguments.items():
            cmd_str = cmd_str.replace(f"{{{key}}}", shlex.quote(str(value)))
        exec_cmd = ["bash", "-c", cmd_str]

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _exec_sync(exec_cmd, _DEFAULT_TIMEOUT, user="computron")),
                timeout=_DEFAULT_TIMEOUT,
            )
        except TimeoutError:
            return {"stdout": None, "stderr": "Timed out after %ss" % _DEFAULT_TIMEOUT, "exit_code": 1}

    else:
        json_args = json.dumps(arguments)
        script_path = "%s/custom_tools/scripts/%s" % (home_dir, tool_def.script_filename)
        interpreter = "python3" if tool_def.language == "python" else "bash"
        cmd_str = "echo %s | %s %s" % (shlex.quote(json_args), interpreter, shlex.quote(script_path))
        exec_cmd = ["bash", "-c", cmd_str]

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _exec_sync(exec_cmd, _DEFAULT_TIMEOUT, user="computron")),
                timeout=_DEFAULT_TIMEOUT,
            )
        except TimeoutError:
            return {"stdout": None, "stderr": "Timed out after %ss" % _DEFAULT_TIMEOUT, "exit_code": 1}

    return result


__all__ = ["execute_custom_tool"]
