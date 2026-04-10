# Container Distribution: Ship Computron as a Single Image

## Context

Computron 9000 currently runs as a **host application** orchestrating a separate Podman container. The host runs aiohttp + React UI; the container provides Xfce + VNC. All tool execution crosses the host-container boundary via Podman SDK exec calls and a shared volume mount.

This refactor **moves the entire app inside the container**. Pull the image, run it, open a browser. One process, one filesystem, one set of paths. The code has no concept of "inside" vs "outside" — it just runs locally.

**Ollama and the inference container remain external** (separate concerns). `InferenceContainerConfig` is unchanged.

### Design Principles

1. **One code path, zero branching.** There is no "container mode" vs "dev mode" in the code. Tools take absolute paths directly — no resolution against a home directory. `run_bash_cmd` uses `home_dir` as its `cwd`, that's it. The config values change between environments, not the code.

2. **No clamping, no workspaces.** The container is the sandbox. Path sanitization, `..` traversal prevention, container prefix stripping, and workspace folder concepts are all removed.

3. **Single Dockerfile.** The existing `container/Dockerfile` is extended with app layers. For rapid dev, source code is volume-mounted into the container.

4. **Browser via CDP.** Google Chrome runs as a persistent process in the container desktop. Browser tools connect over CDP, starting Chrome on demand if needed.

```
┌────────────────────────────────────────────┐
│  Container (single image)                  │
│                                            │
│  ┌─────────────────────────────────────┐   │
│  │  Desktop: Xfce + VNC + Chrome       │   │
│  │  (DISPLAY=:99, VNC :5900, WS :6080) │   │
│  │  Chrome --remote-debugging-port=9222│   │
│  └─────────────────────────────────────┘   │
│                                            │
│  ┌─────────────────────────────────────┐   │
│  │  App: aiohttp + React UI (:8080)    │   │
│  │  agents, tools, all run locally     │   │
│  │  bash → subprocess, files → direct  │   │
│  │  browser → CDP to Chrome            │   │
│  └─────────────────────────────────────┘   │
│                                            │
│  Volumes:                                  │
│    /home/computron (agent workspace, rw)   │
│    /var/lib/computron_9000 (app state, ro) │
└────────────────────────────────────────────┘
         │ podman exec (CLI, unchanged)
         v
┌─────────────────────┐
│ Inference container  │
│ (GPU, separate)      │
└─────────────────────┘
```

### Permission Model

Two users:
- **`computron_app`** — runs the Python app process. Owns state files.
- **`computron`** — runs agent subprocesses (bash commands, scripts). In `computron_app` group for read access to state.

| Path | Owner | Mode | Agent (computron) | App (computron_app) |
|------|-------|------|-------------------|-------------------|
| `/home/computron` | `computron:computron` | `755` | read/write | read/write |
| `/tmp` | (world-writable) | `1777` | read/write | read/write |
| `/var/lib/computron_9000` | `computron_app:computron_app` | `750` | **read only** (via group) | read/write |
| `/opt/computron` | `root:root` | `755` | read only | read only |

Agent subprocesses spawned with explicit user:
```python
proc = await asyncio.create_subprocess_shell(cmd, cwd="/home/computron", user="computron")
```

`computron` has **no sudo access**. Package installs go through a dedicated `install_packages` tool that runs as the app user (`computron_app`):

```
computron_app ALL=(root) NOPASSWD: /usr/bin/apt-get install *
```

The tool handles manager selection:
- `apt` → `sudo apt-get install -y` (via computron_app sudoers)
- `pip` → `pip install --user` as computron → `/home/computron/.local/`
- `npm` → `npm install` as computron → `./node_modules/`

---

## Execution Plan

### Phase 1: Config & Core Infrastructure

#### 1A. Config Simplification (`config/__init__.py`)

**`VirtualComputerConfig`** (lines 165-172) — remove `container_name`, `container_user`, `container_working_dir`. Keep only `home_dir`:

```python
class VirtualComputerConfig(BaseModel):
    home_dir: str   # /home/computron (the agent's working root)
```

**`InferenceContainerConfig`** (lines 174-180) — unchanged. It still needs `container_name`, `home_dir`, `container_working_dir` for the external inference container.

In `load_config()` (line 276): try `config.dev.yaml` first, fall back to `config.yaml`:

```python
dev_path = Path(__file__).parent.parent / "config.dev.yaml"
path = dev_path if dev_path.exists() else Path(__file__).parent.parent / "config.yaml"
```

#### 1B. Update `config.yaml` (container-native paths)

```yaml
settings:
  home_dir: /var/lib/computron_9000    # app state (agent can read, not write)
virtual_computer:
  home_dir: /home/computron            # agent workspace
# inference_container: unchanged
```

Two volumes:
```bash
podman run \
  -v computron_workspace:/home/computron:rw,z \
  -v computron_state:/var/lib/computron_9000:rw,z \
  ...
```

Create `config.dev.yaml` (gitignored) from current `config.yaml` content so existing developer setups aren't broken.

#### 1C. Delete workspace and path utils

**Delete:**
- `tools/virtual_computer/_path_utils.py` — no path resolution needed, agent provides absolute paths
- `tools/virtual_computer/workspace.py` — no workspace concept

**All ~20 `resolve_under_home()` call sites become `Path(path)` directly.** These are in:
- `file_ops.py` — 9 calls (lines 47, 70, 89, 116, 117, 139, 140, 168, 195, 253, 284)
- `read_ops.py` — 2 calls (lines 56, 144)
- `edit_ops.py` — 2 calls (lines 42, 119)
- `search_ops.py` — 1 call (line 141)
- `patching.py` — 2 calls (lines 31, 112)

Currently these return `rel_return_path` (relative path) to the agent. Change to return `str(path)` (the absolute path the agent provided).

**Strip workspace references from:**
- `run_bash_cmd.py` — remove `get_current_workspace_folder()` import and workspace cwd logic (lines 22, 117-119)
- `implementation_artifacts.py` — remove workspace-based plan storage. Plans can use `settings.home_dir / "implementation_plans"` flat, or this module can be simplified/removed entirely.
- `edit_ops.py`, `search_ops.py`, `stat_ops.py` — remove workspace docstring references

**Delete test files:**
- `tests/tools/virtual_computer/test_workspace_resolution.py` — tests the deleted workspace path logic
- `tests/tools/virtual_computer/test_workspace_writes.py` — tests workspace file operations

#### 1D. New `install_packages` tool

New file: `tools/virtual_computer/install_packages.py`

Dedicated tool for package installation. Removes package-install detection from `run_bash_cmd`.

### Phase 2: Podman Exec → Local Subprocess

#### 2A. Bash Commands (`tools/virtual_computer/run_bash_cmd.py`)

Replace Podman SDK with `asyncio.create_subprocess_shell()`.

**Remove:**
- `from podman import PodmanClient` (line 14)
- `from podman.api import stream_frames` (line 15)
- `from podman.domain.containers import Container` (line 16, 25)
- Container lookup logic (lines 88-111)
- Podman API exec machinery (lines 143-249)
- Package-install auto-elevation (lines 125-129)
- Workspace cwd logic (lines 117-119)

**Replace with:**
- `asyncio.create_subprocess_shell(shell_cmd, cwd=home_dir, stdout=PIPE, stderr=PIPE)`
- `cwd` = `config.virtual_computer.home_dir`, always
- Streaming: read stdout/stderr concurrently, publish `TerminalOutputPayload` events
- Exit code: `proc.returncode`

**Keep:** Policy enforcement (`_is_allowed_command` from `_policy.py`), event publishing, timeout handling, strict bash flags (`set -euo pipefail`), `BashCmdResult` model

#### 2B. Desktop Exec (`tools/desktop/_exec.py`)

Replace Podman exec with local async subprocess.

**Remove:**
- `from podman import PodmanClient` (line 7)
- `_strip_stream_headers()` (lines 18-43) — no more Podman stream framing
- `_exec_sync()` function and container lookup (lines 85-101)

**New `_run_desktop_cmd`:**
```python
async def _run_desktop_cmd(cmd, *, display=None, user=None, timeout=30):
    config = load_config()
    if display is None:
        display = _current_display.get() or config.desktop.user_display
    shell_cmd = f"export DISPLAY={display}; {cmd}"
    if user == "root":
        shell_cmd = f"sudo bash -c {shlex.quote(shell_cmd)}"
    proc = await asyncio.create_subprocess_shell(
        shell_cmd, stdout=PIPE, stderr=PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    output = (stdout or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        logger.warning("Desktop cmd exited %d: %s", proc.returncode, cmd)
    return output
```

No more thread executor — pure async subprocess. The `_current_display` ContextVar and `DesktopExecError` stay.

#### 2C. Desktop Screenshot (`tools/desktop/_screenshot.py`)

Remove host↔container path split. Screenshot is written and read locally:

- Remove `host_home = config.virtual_computer.home_dir` (line 32) and host path computation (line 50)
- `scrot` writes to `/tmp/.desktop_screenshot_{display}.png`, we read it directly
- No more `run_in_executor` for file I/O — just read the small file

#### 2D. Custom Tools Executor (`tools/custom_tools/executor.py`)

**Remove:**
- `from podman import PodmanClient` (line 11)
- `from podman.domain.containers import Container` (line 18)
- `_get_container()` (lines 29-42) — container lookup
- Podman container exec in `_exec_sync` (lines 45-68)

**Replace with:** `subprocess.run(cmd, capture_output=True, timeout=timeout)` running locally.
- Dependency installs: `pip install --user` / `npm install` as computron (no sudo)
- Script path: use `config.virtual_computer.home_dir` + relative path (line 139 currently hardcodes `/home/computron/custom_tools/scripts/`)

### Phase 3: Path Translation Removal

All these files translate between `container_working_dir` and `home_dir`. Since there's now one filesystem, collapse the translation.

**Error handling note:** When removing container path validation (e.g., "path must start with /home/computron/"), ensure `FileNotFoundError` and `PermissionError` from the OS are caught and returned as clean tool results (not unhandled exceptions). These replace the old custom validation errors.

#### 3A. `tools/virtual_computer/file_output.py`
- Remove `container_home` prefix check and `host_home` mapping (lines 25-35)
- Path the agent provides IS the real path. Validate it's a file, read it, emit `FileOutputPayload`
- Catch `FileNotFoundError`, `PermissionError` → return error result

#### 3B. `tools/virtual_computer/receive_file.py`
- Remove `container_working_dir` usage (lines 33, 53)
- Write to `config.virtual_computer.home_dir / "uploads"` directly
- Return the actual absolute path (`/home/computron/uploads/filename`)

#### 3C. `tools/virtual_computer/describe_image.py`
- Remove `container_home` / `host_home` translation (lines 45-52)
- Read image bytes directly from the given path
- Catch `FileNotFoundError`, `PermissionError`

#### 3D. `tools/virtual_computer/play_audio.py`
- Same pattern as describe_image — remove path translation (lines 29-39), read directly

#### 3E. `tools/browser/save_content.py`
- Remove `container_working_dir` (line 38) and separate `container_path` construction (line 41)
- `home_dir` IS the path. Save to `home_dir / filename`, return that path

#### 3F. `tools/browser/core/browser.py`
- Remove `_container_dir` instance variable (line 426) entirely
- `_downloads_dir` (line 425) stays — it's the real download path
- Line 1489: remove `_browser._container_dir = config.virtual_computer.container_working_dir`
- Lines 795-796 in `start_ephemeral()`: remove `_container_dir` propagation

#### 3G. `tools/browser/core/_file_detection.py`
- Remove `container_path` field from `DownloadInfo` model (line 46)
- Remove `container_dir` parameter from `save_response_as_file()` (line 81) and `build_download_info_from_path()` (line 187)
- All callers in `browser.py` (lines 497, 1198, 1302) stop passing `container_dir`
- Functions return real filesystem paths only

#### 3H. `tools/generation/generate_image.py` & `generate_music.py`
- These exec into the **inference container** (unchanged, still uses `podman exec` CLI via subprocess)
- Replace `vc_prefix = cfg.virtual_computer.container_working_dir` with `cfg.virtual_computer.home_dir`
  - `generate_image.py` line 136
  - `generate_music.py` line 259
- `ui_path` becomes a real local path since we're inside the container

#### 3I. `server/aiohttp_app.py`
- `container_file_handler` (lines 194-206): use `home_dir` directly (currently uses `home_dir` already for the actual file read — just need to update route prefix)
- Route registration (lines 381-383): change `container_prefix = cfg.virtual_computer.container_working_dir` to `cfg.virtual_computer.home_dir`
- The route becomes `GET /home/computron/{path}` which matches the real filesystem path

### Phase 4: Browser → Chrome CDP

#### 4A. Install Chrome in Container (`container/Dockerfile`)

Add Google Chrome installation layer (after Firefox, around line 52):

```dockerfile
# Google Chrome (for browser automation via CDP)
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] \
      https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
```

#### 4B. Chrome Process Management (new `tools/browser/_chrome_process.py`)

A small module to start Chrome with CDP if not already running:

```python
async def ensure_chrome_running(
    port: int = 9222,
    user_data_dir: str = "",
    display: str = ":99",
) -> str:
    """Ensure Chrome is running with remote debugging. Return the CDP endpoint."""
    endpoint = f"http://localhost:{port}"
    if await _is_chrome_listening(port):
        return endpoint
    cmd = (
        f"DISPLAY={display} google-chrome-stable"
        f" --remote-debugging-port={port}"
        f" --user-data-dir={user_data_dir}"
        f" --no-first-run --no-default-browser-check"
        f" --disable-dev-shm-usage"
        f" --start-maximized"
        " &"
    )
    await asyncio.create_subprocess_shell(cmd)
    await _wait_for_cdp(port, timeout=15)
    return endpoint
```

#### 4C. Browser Core Refactor (`tools/browser/core/browser.py`)

**`Browser.start()` (lines 588-746):** Replace `launch_persistent_context()` with CDP connection.

New class method `Browser.connect_cdp()`:
```python
@classmethod
async def connect_cdp(cls, cdp_url: str, **kwargs) -> Browser:
    pw = await async_playwright().start()
    cdp_browser = await pw.chromium.connect_over_cdp(cdp_url)
    context = cdp_browser.contexts[0]
    await context.set_extra_http_headers(headers)
    await context.add_init_script(anti_bot)
    return cls(context=context, pw=pw, ...)
```

**`_get_root_browser()` (lines 1478-1491):**
```python
async def _get_root_browser() -> Browser:
    global _browser
    if _browser is None:
        config = load_config()
        profile_dir = str(Path(config.settings.home_dir) / "browser" / "profiles" / "default")
        from tools.browser._chrome_process import ensure_chrome_running
        cdp_url = await ensure_chrome_running(user_data_dir=profile_dir)
        _browser = await Browser.connect_cdp(cdp_url)
        _browser._downloads_dir = config.virtual_computer.home_dir
    return _browser
```

**`get_browser()` for sub-agents (lines 1494-1542):**
Sub-agents get their own `BrowserContext` seeded from the default context's full storage state (cookies + localStorage). Isolated tab space, shared logins:

```python
storage = await default_context.storage_state()
new_context = await cdp_browser.new_context(storage_state=storage)
```

Note: IndexedDB / service worker state won't carry over — `storage_state()` covers cookies + localStorage only. Revisit if needed.

**Remove entirely:**
- `start_ephemeral()` classmethod (lines 749-797)
- `_ephemeral_pw_browser` / `_ephemeral_pw` globals and launch logic
- `_container_dir` instance variable and all references

**Keep:** Anti-bot scripts, HTTP headers, download detection (`_file_detection.py` minus `container_path`/`container_dir`), viewport randomization.

### Phase 5: Dockerfile & Entrypoint

#### 5A. Extend `container/Dockerfile`

Add app layers at the end. Move the existing `USER computron` / `WORKDIR` / git config to after the app install:

```dockerfile
# ── App source & dependencies ────────────────────────────────────────
COPY . /opt/computron/
WORKDIR /opt/computron
RUN uv pip install --system --no-cache -e .

# Build UI
RUN cd server/ui && npm ci && npm run build

# ── Users & permissions ──────────────────────────────────────────────
RUN useradd --create-home --shell /bin/bash computron_app && \
    usermod -aG computron_app computron && \
    mkdir -p /var/lib/computron_9000 && \
    chown computron_app:computron_app /var/lib/computron_9000 && \
    chmod 750 /var/lib/computron_9000 && \
    chown -R root:root /opt/computron && \
    chmod -R 755 /opt/computron && \
    echo 'computron_app ALL=(root) NOPASSWD: /usr/bin/apt-get install *' >> /etc/sudoers

# Install gosu for privilege dropping in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER computron
WORKDIR /home/computron
```

#### 5B. Update Entrypoint (`container/entrypoint.sh`)

Entrypoint runs as root (starts desktop), then drops to `computron_app` for the app server:

```bash
#!/bin/bash
export DISPLAY=:99

# Virtual framebuffer + desktop (unchanged)
Xvfb :99 -screen 0 1280x720x24 -ac &
sleep 1
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS
export GTK_MODULES=gail:atk-bridge
export ACCESSIBILITY_ENABLED=1
startxfce4 &
sleep 2
xset s off -dpms 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true
x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -cursor arrow -bg
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

echo "Desktop ready on :99, VNC on 5900, WebSocket on 6080"

# Start app server as computron_app (replaces sleep infinity)
cd /opt/computron
exec gosu computron_app python main.py
```

### Phase 6: Dev Workflow & Build Recipes

#### 6A. Justfile Updates

**New `container-dev` recipe** — mount source code for rapid iteration:

```just
container-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    home_dir=$(awk '/^virtual_computer:/ {found=1} found && /home_dir:/ {print $2; exit}' config.yaml)
    # ... env var setup ...
    podman run -d --rm \
      --name computron_virtual_computer \
      --userns=keep-id \
      --group-add keep-groups \
      --device nvidia.com/gpu=all \
      --network=host \
      $env_args \
      -v "$home_dir:/home/computron:rw,z" \
      -v "$(pwd):/opt/computron:rw,z" \
      computron_9000:latest
```

**Keep `container-start`** for production (no source mount, add state volume).

#### 6B. `.gitignore` — Add `config.dev.yaml`

#### 6C. `pyproject.toml` — Remove `podman` dependency

Remove `"podman==5.4.0.1"`. The inference container uses `podman` CLI via subprocess, not the Python SDK.

### Phase 7: Test Updates

**Delete (workspace tests no longer apply):**
- `tests/tools/virtual_computer/test_workspace_resolution.py`
- `tests/tools/virtual_computer/test_workspace_writes.py`

**Update mock configs** (remove `container_name`, `container_user`, `container_working_dir` from mock `VirtualComputerConfig`):
- `tests/tools/virtual_computer/test_run_bash_cmd_streaming.py` — rewrite: mock subprocess instead of PodmanClient
- `tests/tools/virtual_computer/test_describe_image.py` — remove container path validation tests
- `tests/tools/virtual_computer/test_receive_file.py` — remove container_working_dir from mock, update expected paths
- `tests/tools/virtual_computer/test_implementation_plans.py` — remove workspace references
- `tests/tools/desktop/test_exec.py` — rewrite: mock subprocess instead of PodmanClient
- `tests/tools/test_grounding.py` — unchanged (inference container config untouched)
- `tests/tools/generation/test_generate_music.py` — update `vc_prefix` assertions to use `home_dir`

**Update path assertions** (tools now return absolute paths, not relative):
- `tests/tools/virtual_computer/test_file_system.py`
- `tests/tools/virtual_computer/test_more_file_system.py`
- `tests/tools/virtual_computer/test_read_ops.py`
- `tests/tools/virtual_computer/test_edit_ops.py`
- `tests/tools/virtual_computer/test_search_ops.py`
- `tests/tools/virtual_computer/test_stat_ops.py`
- `tests/tools/virtual_computer/test_apply_text_patch.py`
- `tests/tools/virtual_computer/test_apply_unified_diff.py`
- `tests/tools/virtual_computer/test_prepend_file.py`
- `tests/tools/virtual_computer/test_read_file_or_dir_in_home_dir.py`

---

## Verification

1. `just test` — all tests pass with updated mocks and assertions
2. `just container-build` — image builds with Chrome + app layers + two users
3. `just container-start` — container starts, desktop + app both come up
4. `http://localhost:8080` — UI loads, can chat
5. Agent can: run bash commands, read/write in `/home/computron` and `/tmp`, read `/var/lib/computron_9000`
6. Agent cannot: write to `/var/lib/computron_9000`, modify `/opt/computron`
7. Browser tools: Chrome starts via CDP, pages load, downloads work, sub-agent contexts inherit logins
8. `just container-dev` — source-mounted mode, edit on host, changes reflected in container
9. `install_packages` tool: apt/pip/npm all work with correct permissions
