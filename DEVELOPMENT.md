# Development Guide

## Architecture

Computron 9000 runs as a single container. The app server (aiohttp + React), desktop environment (Xfce + VNC), browser (Chrome), and inference models all live inside one image. Ollama runs on the host and is accessed via `--network=host`.

```
Container (everything runs as computron)
  App server (aiohttp :8080)
    agents/ — LLM agent implementations
    tools/  — tool modules the agent invokes
    server/ — HTTP API + React UI
  Desktop (Xfce + VNC :5900 + noVNC :6080)
    Chrome, Firefox, terminal, file manager
  Inference (GPU models for image/music/video/grounding)

Host
  Ollama — LLM inference (accessed at localhost:11434 via --network=host)
  Docker — container runtime
```

### Key Paths

| Path | Owner | Purpose |
|------|-------|---------|
| `/opt/computron` | root | App source (baked into image; overwritten by tar-pipe on `just dev`/`restart-app`/`rebuild-ui`) |
| `/home/computron` | computron | Agent workspace, downloads, generated files |
| `/var/lib/computron` | computron | Conversations, memory, custom tools, goals |

## Dev Workflow

```sh
just build          # Build image (only when Dockerfile changes)
just dev            # Start dev container, sync source, build UI, launch on :8080
just restart-app    # Sync Python source, bounce the app
just rebuild-ui     # Sync UI source, rebuild dist/
just stop           # Stop container (state persists in ~/.computron_9000/)
just reset          # Stop and wipe state
just shell          # Bash inside the container
just logs           # Tail app + inference logs
```

`just dev` **copies** your repo into the container via a tar-pipe — no bind mount. Source changes on the host don't appear until you run `just restart-app` or `just rebuild-ui`. This keeps the container unable to write back into your repo.

**Note:** `just restart-app` only bounces the Python process. `.env` changes require `just stop && just dev`.

### Config

- `config.yaml` — all configuration. Uses `${ENV_VAR:-default}` syntax. Single source of truth for env vars.
- `.env` — local dev overrides (gitignored). Passed via `--env-file`.

### Feature Flags

| Feature | Env Var | Requires |
|---------|---------|----------|
| Image generation | `ENABLE_IMAGE_GEN=1` | GPU + HF_TOKEN |
| Music generation | `ENABLE_MUSIC_GEN=1` | GPU |
| Desktop agent | `ENABLE_DESKTOP=1` | — |
| Visual grounding | `ENABLE_GROUNDING=1` | GPU |
| Custom tools | `ENABLE_CUSTOM_TOOLS=1` | — |

## Testing

```
tests/
  unit/          # Host-only, no external services
  e2e/           # Playwright browser tests against a running app
  integration/   # Needs a running container with Ollama
```

```sh
just unit           # Unit tests
just e2e            # E2E in a throwaway container on :9090
just integration    # Integration tests (needs COMPUTRON_URL)
just test-file <p>  # Specific file
just test-ui        # Vitest UI tests
```

`just e2e` is self-contained: spawns a throwaway container on :9090, syncs source, builds UI, runs Playwright, tears down. No image rebuild needed.

## Code Quality

```sh
just lint       # ruff check
just typecheck  # mypy
just format     # ruff fix + format
just check      # all three (non-mutating)
```

## Frontend (server/ui/)

- React 18 with JSX (not TypeScript)
- Vite for bundling, Vitest for testing
- CSS Modules (`*.module.css`)
- Function components with hooks

## Conventions

See `CLAUDE.md` for the full coding conventions. Key points:

- Python 3.12, `uv` for deps
- `logger.info("message %s", var)` — no f-strings in logging
- `__init__.py` is a facade — pure re-exports, no code
- Eager imports by default; lazy only for heavy optional deps (playwright, torch)
- Circular imports are a design bug — fix the graph, don't patch around it

## Container Build & Publish

### Multi-Arch Setup (one-time)

The image builds for both `linux/amd64` and `linux/arm64`. On **Linux**, install QEMU first so the kernel can emulate ARM:

```sh
docker run --privileged --rm tonistiigi/binfmt --install all
```

Docker Desktop (macOS/Windows) bundles QEMU — no setup needed.

### Build & Publish

```sh
just build     # Build computron_9000:latest locally (single-arch, for dev)
just publish   # Build + push multi-arch to ghcr.io/lefoulkrod/computron_9000
```

`just publish` tags:
- On `main`: `main`, `main-<sha>`, `latest`
- On feature branch: `<branch>-<sha>`, `<branch>-latest`
- CI also adds semver tags on version tags (`v1.2.3` → `v1.2.3`, `v1.2`, `v1`)

> **CI vs `just publish`:** The GitHub Actions workflow auto-publishes on every push to `main` and version tags. `just publish` is now a manual escape hatch — useful for pushing test images from feature branches without waiting for a merge.

## Justfile Reference

Run `just` (no args) to see all available recipes. Key ones:

| Command | Purpose |
|---------|---------|
| `just build` | Build the container image (only when container/Dockerfile changes) |
| `just dev` | Start dev container, sync source, build UI, launch app on :8080 |
| `just restart-app` | Sync latest Python source and bounce the app |
| `just rebuild-ui` | Sync latest UI source and rebuild dist/ |
| `just stop` | Stop the dev container (state at `~/.computron_9000/` persists) |
| `just reset` | Stop and wipe state |
| `just shell` | Bash shell inside the dev container |
| `just logs` | Tail app + inference logs |
| `just publish` | Build + push multi-arch image (amd64 + arm64) to GHCR |
| `just test` | Run all unit tests |
| `just test-unit` | Run unit tests only |
| `just test-file <path>` | Run tests for a specific file |
| `just e2e` | Run e2e tests in a throwaway container on :9090 |
| `just lint` | Lint with ruff |
| `just typecheck` | Type check with mypy |
| `just format` | Auto-format with ruff |
| `just check` | All non-mutating checks (lint + typecheck + format-check) |
