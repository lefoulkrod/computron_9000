# Development Guide

## Architecture

Computron 9000 runs as a single container. The app server (aiohttp + React), desktop environment (Xfce + VNC), browser (Chrome), and inference models all live inside one image. There is no "host mode" — all development happens through the container.

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
  Ollama (:11434) — LLM inference
  Docker — container runtime
```

### Key Paths

| Path | Owner | Purpose |
|------|-------|---------|
| `/opt/computron_9000` | root | App source (read-only in prod, mounted in dev) |
| `/home/computron` | computron | Agent workspace, downloads, generated files |
| `/var/lib/computron` | computron | Conversations, memory, custom tools, goals |

## Dev Workflow

```sh
# First time: build the image
just container-build

# Start with source code mounted (edit locally, run in container)
just container-dev

# After editing Python files, restart the app server:
just container-restart-app

# Watch logs:
docker logs -f computron_virtual_computer

# Shell into the container:
just container-shell
```

The `container-dev` recipe mounts your local source at `/opt/computron_9000` inside the container. Edit files on your host, restart the app server to pick up changes. The desktop and VNC stay running across restarts.

### Config Files

- `config.yaml` — container paths (`/var/lib/computron`, `/home/computron`).

## Project Structure

```
agents/       Agent implementations (ollama, browser, coder, web, deep_research)
tools/        Tool modules (browser, desktop, virtual_computer, generation, memory, custom_tools)
server/       aiohttp backend + React UI (server/ui/)
models/       Model configuration and completion helpers
sdk/          Internal SDK (events, tool definitions)
utils/        Shared utilities
config/       Configuration loading (Pydantic models)
container/    Dockerfile, entrypoint, inference scripts
tests/        Test suite (mirrors source structure)
main.py       Entry point
```

## Testing

```sh
just test              # All tests
just test-unit         # Unit tests only
just test-file <path>  # Specific file
```

All tests are unit tests — no Ollama, no network, no containers. Tests run on the host with `PYTHONPATH=. uv run pytest`.

### Test Conventions

- Place tests in `tests/` mirroring source structure
- Mark with `@pytest.mark.unit`
- Use descriptive names, Google-style docstrings
- Never patch around test failures

## Code Quality

Only run these when asked:

```sh
just lint       # ruff check
just typecheck  # mypy
just format     # ruff fix + format
just check      # all three (non-mutating)
```

## Python Conventions

- Python 3.12
- Google-style docstrings (no implementation details in docstrings)
- `logger.info("message %s", var)` — not f-strings for logging
- Pydantic for data validation
- Private members: single leading underscore
- Stdlib imports at top of file; lazy imports only for heavy third-party deps
- New deps go in `pyproject.toml` (managed with `uv`)

## Frontend (server/ui/)

- React 18 with JSX (not TypeScript)
- Vite for bundling, Vitest for testing
- CSS Modules (`*.module.css`)
- Function components with hooks

```sh
just ui-dev    # Vite dev server
just ui-build  # Production build
just ui-test   # Vitest
```

## Container Build

```sh
just container-build   # Build image
```

The Dockerfile layers are ordered for cache efficiency:
1. System packages (apt) — rarely changes
2. Python 3.12 setup
3. Agent packages (pip) — general-purpose libraries
4. PyTorch + CUDA (~2.5 GB) — separate layer
5. Image gen deps (diffusers)
6. Music gen deps (ACE-Step)
7. Pre-downloaded models (TAESD, Kokoro)
8. Users, permissions, Xfce config
9. App dependencies (cached on manifest change)
10. App source + UI build (changes every build)

## Justfile Reference

Run `just` to see all available commands. Key ones:

| Command | Purpose |
|---------|---------|
| `just container-build` | Build the container image |
| `just container-start` | Start in production mode |
| `just container-dev` | Start with source mounted |
| `just container-restart-app` | Restart app server (desktop stays up) |
| `just container-stop` | Stop the container |
| `just container-shell` | Shell into the container |
| `just test` | Run all tests |
| `just test-unit` | Run unit tests only |
| `just test-file <path>` | Run tests for a specific file |
| `just lint` | Lint with ruff |
| `just typecheck` | Type check with mypy |
| `just format` | Auto-format with ruff |
