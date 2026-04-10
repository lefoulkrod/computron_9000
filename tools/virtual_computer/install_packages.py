"""Tool for installing system packages via apt.

Runs apt-get with sudo so the agent doesn't need raw ``sudo`` access
in its bash commands.  For pip/npm packages use ``run_bash_cmd`` directly.
"""

import asyncio
import logging
import shlex

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT: float = 300.0


async def install_os_packages(packages: list[str]) -> str:
    """Install OS-level system packages via apt.

    For Python packages use ``run_bash_cmd("pip install ...")``.
    For Node packages use ``run_bash_cmd("npm install ...")``.

    Args:
        packages: Apt package names to install (e.g. ``["ffmpeg", "jq"]``).

    Returns:
        A summary of the installation result.
    """
    if not packages:
        return "Error: No packages specified."

    safe_pkgs = [shlex.quote(p) for p in packages]
    cmd = "sudo -n apt-get update -qq && sudo -n apt-get install -y %s" % " ".join(safe_pkgs)

    logger.info("Installing OS packages: %s", packages)

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
        return "Installed %s.\n%s" % (", ".join(packages), stdout)

    logger.warning("Install exited %d for: %s", exit_code, packages)
    return "Install failed (exit %d).\nstdout: %s\nstderr: %s" % (exit_code, stdout, stderr)
