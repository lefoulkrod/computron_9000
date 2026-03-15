"""Thin client for the persistent grounding server.

Auto-starts the server if it isn't running, then sends grounding
requests and returns parsed action results.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

SERVER_URL = "http://127.0.0.1:18902"
SERVER_SCRIPT = "/opt/inference/grounding_server.py"
_PID_FILE = "/tmp/grounding_server.pid"
# First launch downloads ~31GB of model weights + loads into VRAM.
# Subsequent starts only need ~20s for model loading from cache.
STARTUP_TIMEOUT = 1800  # 30 minutes for first-time download
REQUEST_TIMEOUT = 60


def _health_check():
    """Return True if the server is reachable."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _server_process_alive():
    """Return True if a server process is running."""
    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode("utf-8", errors="replace")
        return "grounding_server" in cmdline
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError, OSError):
        return False


def _kill_server():
    """Kill the running grounding server process."""
    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 9)
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.remove(_PID_FILE)
    except OSError:
        pass
    deadline = time.time() + 10
    while time.time() < deadline:
        if not _server_process_alive():
            break
        time.sleep(0.5)
    time.sleep(3)


def _start_server():
    """Launch the grounding server as a background process."""
    proc = subprocess.Popen(
        ["python3", SERVER_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with open(_PID_FILE, "w") as f:
        f.write(str(proc.pid))


def _ensure_server():
    """Make sure the server is running, starting it if needed."""
    if _health_check():
        return

    if _server_process_alive():
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            time.sleep(1)
            if _health_check():
                return
        raise RuntimeError(
            f"Grounding server did not become healthy within {STARTUP_TIMEOUT}s"
        )

    _start_server()
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        if _health_check():
            return
    raise RuntimeError(
        f"Grounding server did not start within {STARTUP_TIMEOUT}s"
    )


def ground(image_b64, task):
    """Send a grounding request and return the parsed action.

    Args:
        image_b64: Base64-encoded screenshot (PNG or JPEG).
        task: Natural language task description, e.g. "Click the Save button".

    Returns:
        dict with keys: action_type, x, y, thought, action, raw, etc.
    """
    _ensure_server()

    body = json.dumps({"image": image_b64, "task": task}).encode()
    return _post_ground(body)


def ground_from_path(image_path, task):
    """Send a grounding request using an image file path on disk.

    Args:
        image_path: Absolute path to a screenshot file accessible to the server.
        task: Natural language task description, e.g. "Click the Save button".

    Returns:
        dict with keys: action_type, x, y, thought, action, raw, etc.
    """
    _ensure_server()

    body = json.dumps({"image_path": image_path, "task": task}).encode()
    return _post_ground(body)


def _post_ground(body):
    """POST to /ground and return the parsed response."""
    req = urllib.request.Request(
        f"{SERVER_URL}/ground",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode()
        try:
            error_data = json.loads(error_body)
            raise RuntimeError(error_data.get("error", error_body))
        except json.JSONDecodeError:
            raise RuntimeError(error_body)
