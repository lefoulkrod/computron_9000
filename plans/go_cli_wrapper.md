# Go CLI Wrapper

## Goal

Replace the `docker run ...` incantation with a single binary:

```bash
computron start        # pulls image, starts container, opens browser
computron stop         # stops the container
computron logs         # tails app logs
computron status       # is it running? what version? GPU detected?
```

Users shouldn't need to know Docker flags. The binary handles volume setup, GPU passthrough, env vars, port mapping, and version management. It's the only thing they install — Docker and Ollama are the only prerequisites.

## Decisions

- **Docker only** for v1. No Podman support initially — reduces the matrix.
- **Inference stays in the container** on Linux/Windows. Docker + nvidia-container-toolkit handles GPU passthrough. The Go CLI detects GPU and guides users through nvidia-container-toolkit setup if needed.
- **macOS deferred.** Docker Desktop works for CPU features (chat, browse, code). GPU inference on Mac (Metal/MPS) is a future problem — likely requires host-side inference via llama.cpp (UI-TARS), stable-diffusion.cpp (FLUX), and keeping ACE-Step container-only.
- **No Podman, no rootless, no CDI** for v1. Docker group membership on Linux is the accepted cost. Docker Desktop on Windows/Mac handles auth transparently.

## Why Go

- Single static binary, no runtime dependencies
- Cross-compile for linux/amd64, windows/amd64, darwin/amd64, darwin/arm64
- Familiar CLI patterns (cobra, etc.)

## Commands

### `computron start`

The main command. Progressive behavior based on what's available:

1. **Check for Docker** — error with install link if not found.
2. **Check for Ollama** — warn if not running, but don't block (user might be using cloud models).
3. **Pull image if needed** — `ghcr.io/lefoulkrod/computron_9000:latest`. Show progress.
4. **Detect GPU** — check for `nvidia-smi`. If found:
   - Check nvidia-container-toolkit is installed (`nvidia-ctk --version`)
   - If not, print setup instructions and ask to continue without GPU
   - If yes, add `--gpus all`
5. **Build run command** from config + detected capabilities:
   - Always: `--shm-size=256m`, port mappings, `--add-host`, named volumes
   - If GPU detected + toolkit installed: `--gpus all`
   - If env vars set: pass through `HF_TOKEN`, `GITHUB_TOKEN`, `GITHUB_USER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
6. **Start container** — handle name conflicts (remove stopped container with same name).
7. **Wait for ready** — poll `http://localhost:8080` until it responds (with timeout).
8. **Open browser** — `xdg-open` / `open` / `start` depending on OS.

Flags:
- `--no-gpu` — skip GPU detection even if available
- `--no-open` — don't open browser
- `--port N` — override web UI port (default 8080)
- `--vnc` — also expose VNC ports (5900, 6080)
- `--model NAME` — pull this Ollama model before starting (convenience)
- `--detach` — default true, `--detach=false` to tail logs after start
- `--version TAG` — use a specific image tag instead of latest

### `computron stop`

Stop and remove the container. Volumes persist.

### `computron restart`

Stop + start. Useful after `computron update`.

### `computron update`

Pull latest image. If container is running, prompt to restart (or `--yes` to auto-restart).

### `computron logs`

Tail container logs (`docker logs -f computron`). `--inference` flag to show inference server logs specifically.

### `computron status`

Show:
- Running / stopped
- Image version (tag + digest)
- Uptime
- GPU detected (yes/no, which card)
- nvidia-container-toolkit installed (yes/no)
- Ollama reachable (yes/no, which models pulled)
- Ports in use
- Volume sizes

### `computron config`

Manage persistent config (`~/.config/computron/config.yaml` or platform equivalent):

```bash
computron config set hf_token hf_xxx    # saved, passed on next start
computron config set model qwen3:32b    # default chat model
computron config get hf_token
computron config list
```

This replaces needing to remember `-e HF_TOKEN=...` every time.

### `computron shell`

Open an interactive shell inside the container.

### `computron vnc`

Open noVNC in browser (`http://localhost:6080/vnc.html`). Start with `--vnc` ports if not already exposed.

### `computron reset`

Remove volumes and container. Fresh start. Requires `--yes` or interactive confirmation.

## Config File

`~/.config/computron/config.yaml` (XDG on Linux, `~/Library/Application Support/` on macOS, `%APPDATA%` on Windows):

```yaml
gpu: auto                # auto | always | never

# Persisted env vars (so you don't pass them every time)
hf_token: ""
github_token: ""
github_user: ""
telegram_bot_token: ""
telegram_chat_id: ""

# Ollama
ollama_host: ""          # empty = auto-detect (host.docker.internal:11434)
ollama_models:           # pulled on `computron start` if missing
  - qwen3.5:4b

# Container
image: ghcr.io/lefoulkrod/computron_9000:latest
port: 8080
vnc: false               # expose VNC ports by default
```

## Project Structure

```
cli/
├── cmd/
│   └── computron/
│       └── main.go          # cobra root command
├── internal/
│   ├── docker/
│   │   └── docker.go        # all Docker CLI interactions
│   ├── config/
│   │   └── config.go        # load/save config file
│   ├── detect/
│   │   ├── gpu.go           # nvidia-smi + nvidia-ctk checks
│   │   └── ollama.go        # ollama health check, model list
│   └── ui/
│       └── browser.go       # open browser cross-platform
├── go.mod
├── go.sum
├── Makefile                  # build targets per platform
└── goreleaser.yaml           # release automation
```

## Docker Interaction

Shell out to the Docker CLI. Simpler than the Docker SDK, no dependency churn, and the user already has it installed.

## Distribution

### GitHub Releases

Use [GoReleaser](https://goreleaser.com/) to build binaries for all platforms on tag push. Users download from releases page.

### Install Script

```bash
curl -fsSL https://computron.dev/install.sh | sh
```

Detects OS/arch, downloads the right binary, puts it in `/usr/local/bin/` (or `~/.local/bin/`).

### Package Managers (later)

- Homebrew tap (macOS/Linux)
- AUR (Arch)
- Scoop (Windows)

## UX Principles

1. **Zero-config works.** `computron start` with nothing else configured should get you a running instance.
2. **Auto-detect everything.** GPU, Ollama — detect and use if available, skip gracefully if not.
3. **Progressive disclosure.** Basic usage needs no flags. Power users get `config` and per-command flags.
4. **Clear errors.** If Docker isn't installed, say so and link to install docs. If Ollama is down, warn but don't block. If a port is taken, suggest an alternative.
5. **No silent failures.** If GPU detection fails, say "No GPU detected, starting without GPU support" — don't just silently omit `--gpus all`.

## Open Questions

- **Ollama model management**: Should `computron start` auto-pull the vision model (`qwen3.5:4b`) if missing? It's required for the desktop agent. Could be annoying if Ollama is slow. Maybe prompt: "Vision model not found. Pull now? (3 GB) [Y/n]"
- **Update channel**: Auto-update check on `computron start`? Or just `computron update` as explicit action? Auto-checks are nice but can be annoying.
- **nvidia-container-toolkit install**: Should the CLI offer to install it automatically (needs sudo)? Or just print instructions and link to docs?
- **Windows GPU**: Docker Desktop + WSL2 + NVIDIA. Works but fragile — depends on driver version and WSL2 kernel. Document as "works but not guaranteed" initially.

## Future (v2+)

- **macOS GPU**: Host-side inference server using llama.cpp (UI-TARS grounding), stable-diffusion.cpp (FLUX image gen). ACE-Step (music) stays container-only — no viable non-Python implementation exists. The Go CLI would manage the host inference process alongside the container.
- **Podman support**: Detect Podman, translate flags (`--gpus all` → `--device nvidia.com/gpu=all`). Rootless Podman + CDI for Linux users who want to avoid the Docker group.
- **Slim image**: Multi-arch (x86_64 + arm64) image without GPU deps for Mac and CPU-only users. ~3GB vs ~9GB.

## Implementation Order

1. **Skeleton** — cobra CLI, `start` / `stop` / `logs` / `status` commands
2. **Config** — persistent config file, env var passthrough
3. **GPU detection** — nvidia-smi + nvidia-ctk checks, flag injection, guided setup
4. **Polish** — `update`, `reset`, `vnc`, `shell`, browser open, health wait
5. **Release** — goreleaser, install script, README update
