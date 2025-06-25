# Justfile for computron_9000 project

# Run the main application with the adk agent SDK
run-adk:
    AGENT_SDK=adk uv run main.py

# Run the main application with pydantic agent SDK
run-pydantic:
    AGENT_SDK=pydantic uv run main.py

# Add a new dependency to the project
add-dep package:
    uv add {{package}}
    
# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# Run all tests (including async tests)
test:
    uv run pytest

# Install all main and test dependencies
install-all:
    uv pip install -r pyproject.toml --extra test
