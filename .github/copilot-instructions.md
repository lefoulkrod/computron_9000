# Copilot Custom Instructions

- Use Google‑style docstrings
- Do not use f-strings for logging; use `logger.info("message %s", var)` instead
- Handle exceptions with context‑aware logging; use module-level logger (`logger = logging.getLogger(__name__)`)
- Use custom exceptions where appropriate
- Write tests for new features/bugs; descriptive names, Google-style docstrings; place in `tests/` mirroring source structure
- Add `@pytest.mark.unit` for unit tests, `@pytest.mark.integration` for integration tests
- run unit tests with `just test-unit`
- Include new deps in pyproject.toml
- Use Pydantic for data validation; ensure JSON-serializable API responses
- Private fields/methods get a single leading underscore
- Always include `__init__.py` for public re-exports, avoid exporting private members, do not export internal functions/classes
- You may ignore Ruff(I001)
