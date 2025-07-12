# Justfile for computron_9000 project
# For details about Just command runner: https://github.com/casey/just

# Default recipe to run when just is called without arguments
default:
    @just --list

# === Application Runners ===

# Run the main application with the default agent SDK
run:
    uv run main.py

# Run the main application with the adk agent SDK
run-adk:
    AGENT_SDK=adk uv run main.py

# Run the main application with pydantic agent SDK
run-pydantic:
    AGENT_SDK=pydantic uv run main.py

# Run the main application with ollama agent SDK
run-ollama:
    AGENT_SDK=ollama uv run main.py

# Start the application with a specific model (default is ollama SDK)
run-with-model model="gemma:7b":
    AGENT_SDK=ollama MODEL={{model}} uv run main.py

# Start Ollama server if not already running
start-ollama:
    ./start_ollama.sh

# === Development Tools ===

# Setup complete development environment
setup-dev: install-all
    systemctl --user enable --now podman.socket
    @echo "Development environment ready. Use 'just run' to start the application."

# Create and activate virtual environment
create-venv:
    uv venv .venv
    @echo "Virtual environment created. Activate it with: source .venv/bin/activate"
    
# Add a new dependency to the project
add-dep package:
    uv add {{package}}

# Remove a dependency from the project
remove-dep package:
    uv remove {{package}}
    
# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# === Testing ===

# Run all tests (including async tests)
test:
    PYTHONPATH=. uv run pytest

# Run only unit tests
test-unit:
    PYTHONPATH=. uv run pytest -m unit

# Run only integration tests
test-integration:
    PYTHONPATH=. uv run pytest -m integration

# Run tests with coverage report
test-coverage:
    PYTHONPATH=. uv run pytest --cov=. --cov-report=term-missing

# === Dependency Management ===

# Install all main and test dependencies
install-all:
    uv pip install -r pyproject.toml --extra test
    @echo "All dependencies installed successfully"

# Upgrade all upgradable packages to the latest compatible versions
upgrade-all:
    uv pip install --upgrade -r pyproject.toml

# === System Checks ===

# Verify system requirements are met
check-system:
    @echo "Checking system requirements..."
    @python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
    @which podman || echo "WARNING: Podman not found. Install it for code execution tools."
    @systemctl --user status podman.socket || echo "WARNING: Podman socket not running. Use 'systemctl --user enable --now podman.socket'"
    @curl -s http://localhost:11434/api/version || echo "WARNING: Ollama not running. Start it with './start_ollama.sh'"
    @echo "System check complete."
