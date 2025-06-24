# Justfile for computron_9000 project

# Run the main application
run:
    uv run main.py

# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# Run all tests (including async tests)
test:
    pytest

# Install all main and test dependencies
install-all:
    uv pip install -r pyproject.toml --extra test
