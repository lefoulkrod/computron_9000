"""Tool for installing system and language packages.

Runs package managers with elevated privileges so the agent doesn't
need raw ``sudo`` access in its bash commands.
"""

import asyncio
import logging
import shlex

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT: float = 300.0

_SUPPORTED_MANAGERS = frozenset({"apt", "pip", "npm"})


class InstallPackagesResult(BaseModel):
    """Result from a package installation."""

    stdout: str | None
    stderr: str | None
    exit_code: int


async def install_packages(
    packages: list[str],
    manager: str = "apt",
) -> InstallPackagesResult:
    """Install one or more packages using the specified package manager.

    Args:
        packages: Package names to install.
        manager: One of ``"apt"``, ``"pip"``, or ``"npm"``.

    Returns:
        InstallPackagesResult with stdout, stderr, and exit code.
    """
    if not packages:
        return InstallPackagesResult(stdout=None, stderr="No packages specified", exit_code=1)

    manager = manager.lower().strip()
    if manager not in _SUPPORTED_MANAGERS:
        return InstallPackagesResult(
            stdout=None,
            stderr="Unsupported manager %r. Use one of: %s" % (manager, ", ".join(sorted(_SUPPORTED_MANAGERS))),
            exit_code=1,
        )

    safe_pkgs = [shlex.quote(p) for p in packages]

    if manager == "apt":
        cmd = "sudo -n apt-get update -qq && sudo -n apt-get install -y %s" % " ".join(safe_pkgs)
    elif manager == "pip":
        cmd = "sudo -n pip install %s" % " ".join(safe_pkgs)
    else:
        cmd = "sudo -n npm install -g %s" % " ".join(safe_pkgs)

    logger.info("Installing packages (%s): %s", manager, packages)

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=_INSTALL_TIMEOUT,
        )
    except TimeoutError:
        logger.error("Package install timed out after %ss", _INSTALL_TIMEOUT)
        return InstallPackagesResult(
            stdout=None,
            stderr="Install timed out after %ss" % _INSTALL_TIMEOUT,
            exit_code=1,
        )
    except Exception as exc:
        logger.exception("Package install failed")
        return InstallPackagesResult(stdout=None, stderr="Install failed: %s" % exc, exit_code=1)

    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace").strip() or None
    stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip() or None

    if proc.returncode == 0:
        logger.info("Successfully installed: %s", packages)
    else:
        logger.warning("Install exited %d for: %s", proc.returncode, packages)

    return InstallPackagesResult(stdout=stdout, stderr=stderr, exit_code=proc.returncode or 0)
