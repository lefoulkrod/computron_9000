# CLAUDE.md

## Project Overview

Computron 9000 is an AI assistant platform with a Python/aiohttp backend and React frontend. It uses Ollama for LLM inference, Podman for sandboxed code execution, and Playwright for browser automation.

### Project Structure

- `agents/` — Agent implementations (ollama, browser, coder, web, deep_research, etc.)
- `tools/` — Tool modules the agent can invoke (browser, code, virtual_computer, memory, custom_tools, web, fs, etc.)
- `server/` — aiohttp backend API (`aiohttp_app.py`) and React UI (`server/ui/`)
- `models/` — Model configuration and completion helpers
- `sdk/` — Internal SDK (events, tool definitions)
- `utils/` — Shared utilities (cache, shutdown)
- `config/` — Configuration loading
- `tests/` — Unit test suite, mirrors source structure
- `e2e/` — Playwright end-to-end browser tests
- `main.py` — Application entry point

## Commands

### Image (rebuild only when container/Dockerfile changes)
- `just build` — Build the container image `computron_9000:latest`
- `just publish` — Tag and push to GHCR

### Dev loop (the container owns the runtime; source is synced in at each step)
- `just dev` — Start dev container (if needed), sync source, build UI, launch app on :8080
- `just restart-app` — Sync latest Python source, bounce the app
- `just rebuild-ui` — Sync latest UI source, rebuild dist/
- `just stop` — Stop the dev container (state at `~/.computron_9000/` persists)
- `just reset` — Stop and wipe `~/.computron_9000/`
- `just shell` — Bash inside the dev container
- `just logs` — Tail app + inference logs

### Testing
- `just test` — Run all unit tests (`PYTHONPATH=. uv run pytest`)
- `just test-unit` — Run unit tests only (`PYTHONPATH=. uv run pytest -m unit`)
- `just test-file <path>` — Run tests for a specific file
- `just test-ui` — Run Vitest UI tests
- `just e2e` — Run Playwright e2e in a throwaway container with fresh state (does NOT rebuild the image)

### Quality (only run when asked)
- `just lint` — Lint with ruff (`uv run ruff check .`)
- `just typecheck` — Type check with mypy (`uv run mypy .`)
- `just format` — Auto-format with ruff (`uv run ruff check --fix . && uv run ruff format .`)
- `just check` — Run all quality checks (lint + typecheck + format-check)

## Python Conventions

- Use Google-style docstrings
- Do not use f-strings for logging; use `logger.info("message %s", var)` instead
- Handle exceptions with context-aware logging; use module-level logger (`logger = logging.getLogger(__name__)`)
- Use custom exceptions where appropriate
- Use Pydantic for data validation; ensure JSON-serializable API responses
- Private and internal fields, methods, functions, constants, types and modules should all be named with a single leading underscore
- Always include `__init__.py` for public re-exports, avoid exporting private members, do not export internal functions/classes
- Include new deps in pyproject.toml (managed with `uv`)
- No backward compatible refactors unless prompted
- Write python code compatible with Python 3.12.10
- Never put implementation details in docstrings
- Add comments to explain non-obvious code
- Import from the submodule, not the package — `from tools.virtual_computer.describe_image import describe_image`, not `from tools.virtual_computer import describe_image`. Package `__init__.py` re-exports are for external consumers; internal code should import from the defining module to avoid shadowing issues with lazy imports.
- You may ignore Ruff(I001)

## Testing Conventions

- Write tests for new features/bugs; descriptive names, Google-style docstrings
- Place tests in `tests/` mirroring source structure
- Add `@pytest.mark.unit` for unit tests
- Only run tests when instructed or before committing.
- Only run quality checks when asked
- NEVER PATCH AROUND TEST FAILURES
  - Do not introduce logic changes that bypass failing tests.
  - Do not add "if" guards, mocks, or fallback logic just to quiet tests.
  - Missing stubs or incomplete fakes are testing bugs, not production logic problems.

## Frontend Conventions (server/ui/)

- React 18 with JSX (not TypeScript)
- Vite for bundling, Vitest for testing
- CSS Modules for styling (`*.module.css` per component)
- Function components with hooks (no class components)
