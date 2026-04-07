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

# After editing .env (feature flags, tokens), restart the container:
just container-stop && just container-dev

# Watch logs:
just container-logs

# Shell into the container:
just container-shell
```

The `container-dev` recipe mounts your local source at `/opt/computron_9000` inside the container. Edit files on your host, restart the app server to pick up changes. The desktop and VNC stay running across app restarts.

**Note:** `container-restart-app` only restarts the Python process. Environment variable changes (`.env`) require a full container restart since they're baked in at `docker run` time.

### Config

- `config.yaml` — all configuration. Uses `${ENV_VAR:-default}` syntax for env var overrides. This is the single source of truth for what env vars the app reads.
- `.env` — local dev overrides (gitignored). Passed to the container via `--env-file`.
- `config.dev.yaml` — optional path override for dev (gitignored).

### Feature Flags

Optional capabilities are disabled by default and enabled via env vars:

| Feature | Env Var | Requires |
|---------|---------|----------|
| Image generation | `ENABLE_IMAGE_GEN=1` | GPU + HF_TOKEN |
| Music generation | `ENABLE_MUSIC_GEN=1` | GPU |
| Desktop agent | `ENABLE_DESKTOP=1` | — |
| Visual grounding | `ENABLE_GROUNDING=1` | GPU |
| Custom tools | `ENABLE_CUSTOM_TOOLS=1` | — |

Set these in `.env` for dev. Feature flags gate: tool registration, agent system prompts, skill registry, and UI elements.

## Project Structure

```
agents/       Agent implementations (computron, browser, coder, desktop, deep_research)
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

## Container Build & Publish

```sh
just container-build   # Build image
just publish           # Tag and push to ghcr.io/lefoulkrod/computron_9000
```

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
| `just container-logs` | Tail app logs |
| `just publish` | Tag and push image to registry |
| `just test` | Run all tests |
| `just test-unit` | Run unit tests only |
| `just test-file <path>` | Run tests for a specific file |
| `just lint` | Lint with ruff |
| `just typecheck` | Type check with mypy |
| `just format` | Auto-format with ruff |
