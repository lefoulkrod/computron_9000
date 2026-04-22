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
- Leading-underscore naming follows the **"private module, public-within-package"** split. The underscore on a module filename is the "internal to this project" signal; symbols inside that module use the underscore only when they're *also* module-local:
  - **Modules (files) and packages (directories)** that are internal to their parent package: leading underscore on the name (`_rpc.py`, `_common/`).
  - **Symbols inside an internal module** (functions, classes, constants, type aliases): leading underscore only when they're used solely inside the module that defines them. Symbols imported by other modules in the same package do not carry the underscore — the containing module's underscore is the "internal" signal. Example: `brokers/_common/_env.py` exports `env_required` (no underscore) because `brokers/email_broker/__main__.py` imports it; `brokers/_common/_rpc.py` keeps `_encode_frame` underscored because it's only used inside `_rpc.py`.
  - **Class members** (methods, instance attributes): leading underscore for anything not part of the class's public surface.
  - This matches PEP 8's "weak internal-use indicator" reading and avoids false-positive "unused private name" warnings from Pylance / Pyright on cross-module imports inside a private package.
- Include new deps in pyproject.toml (managed with `uv`)
- No backward compatible refactors unless prompted
- Write python code compatible with Python 3.12.10
- Never put implementation details in docstrings
- Add comments to explain non-obvious code
- You may ignore Ruff(I001)

## Module Structure

1. **`__init__.py` is a facade — pure re-exports, no code lives there.** If you're writing a function body or defining a singleton in `__init__.py`, move it to a submodule and re-export from `__init__.py`. Avoid exporting private members.
2. **Imports go at the top of the file, eagerly.** Do not reach for lazy imports by default. Eager-import cost is almost always negligible; the cost of cycles, shadowed attributes, and hard-to-trace bugs is not.
3. **Do not use `__getattr__` at package level.** It bypasses normal imports, collapses type info to `Any`, and has a shadowing foot-gun: once any submodule is imported directly, the submodule wins over `__getattr__` and callers silently get a module instead of the function they asked for.
4. **Internal code imports from the defining submodule, not from the package root.** `from tasks import get_store` is for *external consumers*. Inside the `tasks/` package, import from `tasks._singleton`. This is what prevents cycles — the package root re-exports outward, internal modules depend inward.
5. **Types live in modules with no internal dependencies.** A file like `agents/types.py` that only imports stdlib + pydantic can be imported from anywhere without cycle risk. Mixing types with behavior (that imports other things) creates transitive dependencies that cycle easily.
6. **Circular imports are a design bug, not a fact of life. Fix the graph, don't patch around it.** The fix is structural: move the shared thing down a layer (a dedicated leaf module that both sides depend on). Function-local imports and `# noqa: E402` ordering tricks are last-resort escape hatches, not design choices.
7. **Exception to rule 2:** genuinely heavy / optional third-party deps (playwright, torch, transformers) belong in function-local imports inside the feature that needs them — so the rest of the app starts up fast. "Heavy" means hundreds of milliseconds or gigabytes of RAM, not 20ms convenience.

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
