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
# First time (or after Dockerfile changes): build the image
just build

# Start the dev container, sync source into it, build UI, launch the app:
just dev

# After editing Python files, sync the new source and bounce the app:
just restart-app

# After editing UI source, re-sync and rebuild dist/:
just rebuild-ui

# After editing .env (feature flags, tokens), restart the container:
just stop && just dev

# Watch logs:
just logs

# Shell into the container:
just shell
```

`just dev` **copies** your repo into the container via a tar-pipe — it does not bind-mount. Source changes on the host don't appear inside the running container until you run `just restart-app` or `just rebuild-ui`, which re-syncs and bounces the relevant process. This keeps the container unable to write back into your repo (an agent running inside can't pollute the tree) and matches production behavior.

**Note:** `just restart-app` only restarts the Python process. Environment variable changes (`.env`) require a full container restart since they're baked in at `docker run` time.

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
just test              # All unit tests
just test-unit         # Unit tests only
just test-file <path>  # Specific file
just e2e               # E2E browser tests (container must be running)
just e2e-install       # Install Playwright browsers (one-time)
```

### Unit Tests

All unit tests run on the host — no Ollama, no network, no containers. Tests run with `PYTHONPATH=. uv run pytest`.

- Place tests in `tests/` mirroring source structure
- Mark with `@pytest.mark.unit`
- Use descriptive names, Google-style docstrings
- Never patch around test failures

### E2E Tests

End-to-end tests use Playwright (Python) to drive a real browser against a running app. Tests live in `e2e/` at the repo root.

```sh
just e2e
```

`just e2e` is self-contained: it spawns a throwaway container on port 9090 with ephemeral state (so it can run alongside your `just dev` container on 8080), syncs the latest source, builds the UI, runs the tests, and tears everything down at the end. No container image rebuild — it uses the current `computron_9000:latest` image.

- Tests run headless by default
- `just setup` installs Playwright browsers automatically on the host

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
- New deps go in `pyproject.toml` (managed with `uv`)

### Module Structure

See `CLAUDE.md` for the full rules. Short version:

- `__init__.py` is a facade — pure re-exports, no code.
- Imports go at the top of the file, eagerly. No package-level `__getattr__`. No lazy imports except for genuinely heavy optional deps (playwright, torch).
- Internal modules import from the defining submodule, not from the package root. `from tasks._singleton import get_store`, not `from tasks import get_store`, when inside the `tasks/` package.
- Types live in modules that have no internal dependencies (e.g. `agents/types.py`).
- Circular imports mean the module graph is wrong — fix the graph, don't patch around it.

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
just build     # Build computron_9000:latest (only when Dockerfile changes)
just publish   # Tag and push to ghcr.io/lefoulkrod/computron_9000
```

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
| `just publish` | Tag and push image to registry |
| `just test` | Run all unit tests |
| `just test-unit` | Run unit tests only |
| `just test-file <path>` | Run tests for a specific file |
| `just e2e` | Run e2e tests in a throwaway container on :9090 |
| `just lint` | Lint with ruff |
| `just typecheck` | Type check with mypy |
| `just format` | Auto-format with ruff |
| `just check` | All non-mutating checks (lint + typecheck + format-check) |
