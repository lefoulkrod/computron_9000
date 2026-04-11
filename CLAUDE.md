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

### Running
- `just run` — Start the app
- `just dev` — Start with auto-reload
- `just dev-full` — Start backend + UI dev server together

### Testing
- `just test` — Run all unit tests (`PYTHONPATH=. uv run pytest`)
- `just test-unit` — Run unit tests only (`PYTHONPATH=. uv run pytest -m unit`)
- `just test-file <path>` — Run tests for a specific file
- `just e2e` — Run Playwright e2e tests (container must be running on :8080)

### Quality (only run when asked)
- `just lint` — Lint with ruff (`uv run ruff check .`)
- `just typecheck` — Type check with mypy (`uv run mypy .`)
- `just format` — Auto-format with ruff (`uv run ruff check --fix . && uv run ruff format .`)
- `just check` — Run all quality checks (lint + typecheck + format-check)

### UI
- `just ui-dev` — Start Vite dev server
- `just ui-build` — Production build
- `just ui-test` — Run UI tests (Vitest)

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
