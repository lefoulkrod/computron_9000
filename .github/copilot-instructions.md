# Copilot Custom Instructions

- Format imports per PEP 8: standard → third-party → local, with blank line separators
- Use Google‑style docstrings with Args/Returns/Raises
- Add type hints to all function signatures; enforce mypy `--strict` (full annotations, no untyped defs/calls, explicit Optional, generics, missing-imports, re-exports)
- Prefer async/await for I/O operations
- Do not use f-strings for logging; use `logger.info("message %s", var)` instead
- Keep functions/classes small, focused
- Handle exceptions with context‑aware logging; use module-level logger (`logger = logging.getLogger(__name__)`)
- Use custom exceptions where appropriate
- Write tests for new features/bugs; descriptive names, Google-style docstrings; place in `tests/` mirroring source structure
- Document public APIs and update README/docs
- Include new deps in pyproject.toml
- Use minimal, well-maintained libraries; avoid hardcoded secrets
- Use Pydantic for data validation; ensure JSON-serializable API responses
- Private fields/methods get a single leading underscore
- Always include `__init__.py` for public re-exports, avoid exporting private members, do not export internal functions/classes
- Ensure code passes lint and type checking by using `just check` command or the equivalent `uv` commands (refer to justfile)
