# Justfile for computron_9000 project

# Run the main application with the adk agent SDK
run-adk:
    AGENT_SDK=adk uv run main.py

# Run the main application with pydantic agent SDK
run-pydantic:
    AGENT_SDK=pydantic uv run main.py

# Run the main application with ollama agent SDK
run-ollama:
    AGENT_SDK=ollama uv run main.py
    
# Add a new dependency to the project
add-dep package:
    uv add {{package}}

# Remove a dependency from the project
remove-dep package:
    uv remove {{package}}
    
# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# Run all tests (including async tests)
test:
    PYTHONPATH=. uv run pytest

# Run only unit tests
test-unit:
    PYTHONPATH=. uv run pytest -m unit

# Run only integration tests
test-integration:
    PYTHONPATH=. uv run pytest -m integration

# Install all main and test dependencies
install-all:
    uv pip install -r pyproject.toml --extra test

# Upgrade all upgradable packages to the latest compatible versions
upgrade-all:
    uv pip install --upgrade -r pyproject.toml
