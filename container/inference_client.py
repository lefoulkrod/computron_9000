"""Thin client for the persistent inference server.

Auto-starts the server if it isn't running, then sends a generation
request and returns the output file path.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

SERVER_URL = "http://127.0.0.1:18901"
SERVER_SCRIPT = "/opt/inference/inference_server.py"
_PID_FILE = "/tmp/inference_server.pid"
STARTUP_TIMEOUT = 120  # max seconds to wait for server to come up
REQUEST_TIMEOUT = 600  # max seconds to wait for generation


def _health_check():
    """Return True if the server is reachable."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _server_process_alive():
    """Return True if a server process is running (even if not yet healthy)."""
    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
        # Check if process exists and is not a zombie
        os.kill(pid, 0)
        # Verify it's actually an inference server, not a recycled PID
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode("utf-8", errors="replace")
        return "inference_server" in cmdline
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError, OSError):
        return False


def _kill_server():
    """Kill the running inference server process and wait for GPU memory release."""
    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 9)  # SIGKILL — NF4 weights prevent clean exit
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.remove(_PID_FILE)
    except OSError:
        pass
    # Wait for the process to actually die
    deadline = time.time() + 10
    while time.time() < deadline:
        if not _server_process_alive():
            break
        time.sleep(0.5)
    # Give the nvidia driver time to reclaim VRAM after process death.
    # Without this delay, a new server may start before GPU memory is freed,
    # causing OOM during model loading.
    time.sleep(3)


def _start_server():
    """Launch the inference server as a background process."""
    proc = subprocess.Popen(
        ["python3", SERVER_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Write PID file so subsequent clients know a server is starting
    with open(_PID_FILE, "w") as f:
        f.write(str(proc.pid))


def _ensure_server():
    """Make sure the server is running, starting it if needed."""
    if _health_check():
        return

    # Don't spawn a new server if one is already starting up
    if _server_process_alive():
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            time.sleep(1)
            if _health_check():
                return
        raise RuntimeError(f"Inference server did not become healthy within {STARTUP_TIMEOUT}s")

    _start_server()
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        if _health_check():
            return
    raise RuntimeError(f"Inference server did not start within {STARTUP_TIMEOUT}s")


def generate(gen_type, description, **params):
    """Send a generation request and return the output path.

    Args:
        gen_type: "image" or "video"
        description: Text prompt for generation.
        **params: Optional overrides (model, num_frames, height, width).

    Returns:
        Absolute path to the generated file.
    """
    _ensure_server()

    body = {"type": gen_type, "description": description}
    body.update(params)

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode()
        try:
            error_data = json.loads(error_body)
            # Server needs to restart for a different model
            if error_data.get("restart_required"):
                _kill_server()
                _ensure_server()
                return generate(gen_type, description, **params)
            raise RuntimeError(error_data.get("error", error_body))
        except json.JSONDecodeError:
            raise RuntimeError(error_body)

    if "error" in result:
        raise RuntimeError(result["error"])
    return result["path"]


def generate_stream(gen_type, description, **params):
    """Send a streaming generation request and yield progress dicts.

    Each yielded dict has at least a "status" key. Example sequence:
        {"status": "loading", "message": "Loading klein-4b..."}
        {"status": "generating", "step": 1, "total_steps": 4, "preview": "base64..."}
        {"status": "complete", "path": "/home/computron/generated_images/xxx.png"}

    If the server needs to restart for a different model, this function
    handles the restart transparently and re-yields from the new server.

    Args:
        gen_type: "image" or "video"
        description: Text prompt for generation.
        **params: Optional overrides (model, num_frames, height, width).

    Yields:
        dict: Progress events from the inference server.
    """
    _ensure_server()

    body = {"type": gen_type, "description": description}
    body.update(params)

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/generate-stream",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Server says it needs to restart for a different model
                if event.get("status") == "restart_required":
                    model = event.get("model", "")
                    yield {"status": "loading",
                           "message": f"Restarting server for {model}..."}
                    _kill_server()
                    _ensure_server()
                    yield from generate_stream(gen_type, description, **params)
                    return
                yield event
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode()
        try:
            error_data = json.loads(error_body)
            # Non-streaming restart response (409 status code)
            if error_data.get("restart_required"):
                model = error_data.get("model", "")
                yield {"status": "loading",
                       "message": f"Restarting server for {model}..."}
                _kill_server()
                _ensure_server()
                yield from generate_stream(gen_type, description, **params)
                return
            yield {"status": "failed", "message": error_data.get("error", error_body)}
        except json.JSONDecodeError:
            yield {"status": "failed", "message": error_body}
