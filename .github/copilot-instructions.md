# Copilot Custom Instructions

- Use Google‑style docstrings
- Do not use f-strings for logging; use `logger.info("message %s", var)` instead
- Handle exceptions with context‑aware logging; use module-level logger (`logger = logging.getLogger(__name__)`)
- Use custom exceptions where appropriate
- Write tests for new features/bugs; descriptive names, Google-style docstrings; place in `tests/` mirroring source structure
- Add `@pytest.mark.unit` for unit tests, `@pytest.mark.integration` for integration tests
- Run unit tests  (UI or Python) after every related change
- Include new deps in pyproject.toml
- Use Pydantic for data validation; ensure JSON-serializable API responses
- Private and internal fields, methods, functions, constants, types and modules should all be named with a single leading underscore
- Always include `__init__.py` for public re-exports, avoid exporting private members, do not export internal functions/classes
- You may ignore Ruff(I001)
- No backward compatible refactors unless prompted
- Write python code compatible with the current Python version 3.12.10
- Never put implementation details in docstrings
- Add comments to explain non-obvious code
