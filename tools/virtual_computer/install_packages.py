"""Tool for installing system and language packages.

Runs package managers with elevated privileges so the agent doesn't
need raw ``sudo`` access in its bash commands.
"""

import asyncio
import logging
import shlex

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT: float = 300.0

_SUPPORTED_MANAGERS = frozenset({"apt", "pip", "npm"})


async def install_packages(
    packages: list[str],
    manager: str = "apt",
) -> str:
    """Install one or more packages using the specified package manager.

    Args:
        packages: Package names to install.
        manager: One of ``"apt"``, ``"pip"``, or ``"npm"``.

    Returns:
        A summary of the installation result.
    """
    if not packages:
        return "Error: No packages specified."

    manager = manager.lower().strip()
    if manager not in _SUPPORTED_MANAGERS:
        return "Error: Unsupported manager %r. Use one of: %s" % (manager, ", ".join(sorted(_SUPPORTED_MANAGERS)))

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
        return "Error: Install timed out after %ss." % _INSTALL_TIMEOUT
    except Exception as exc:
        logger.exception("Package install failed")
        return "Error: Install failed: %s" % exc

    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
    stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
    exit_code = proc.returncode or 0

    if exit_code == 0:
        logger.info("Successfully installed: %s", packages)
        return "Installed %s via %s.\n%s" % (", ".join(packages), manager, stdout)

    logger.warning("Install exited %d for: %s", exit_code, packages)
    return "Install failed (exit %d).\nstdout: %s\nstderr: %s" % (exit_code, stdout, stderr)
