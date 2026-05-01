"""Generic e2e infrastructure helpers — container interaction, etc.

Not pytest fixtures — plain functions imported by the test files
that need them. Anything that needs pytest discovery belongs in
conftest.py or a registered plugin module.
"""

import os
import subprocess

CONTAINER_NAME = os.environ.get("COMPUTRON_CONTAINER", "computron_e2e")


def container_exec(script: str) -> str:
    """Run a Python snippet inside the running computron container.

    Used for seeding state that has no HTTP API (goals, runs, etc.). The
    snippet executes in the same Python environment as the running app —
    `from tasks import get_store` works, file writes land in the volume
    the app reads from.

    Runs as `computron` (the user the app runs as) so any files written
    are owned by the same uid as the app process. Otherwise the app's
    later cleanup hits a PermissionError.
    """
    result = subprocess.run(
        ["docker", "exec", "-u", "computron", "-w", "/opt/computron",
         CONTAINER_NAME, "python3.12", "-c", script],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def container_run_root(cmd: str) -> str:
    """Run a shell command inside the container as root.

    For setup/teardown ops that need privileges the app user doesn't
    have — chmod on broker-owned files in /run/cvault, /etc/hosts edits,
    process signals to the supervisor. Use sparingly; tests that touch
    state managed by the app should prefer `container_exec` (runs as
    the app's uid) so the app can read/clean up afterwards.
    """
    result = subprocess.run(
        ["docker", "exec", "-u", "0", CONTAINER_NAME, "bash", "-c", cmd],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()
