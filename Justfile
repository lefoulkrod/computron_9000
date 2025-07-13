# Justfile for computron_9000 project

# Default recipe - show available commands
default:
    @just --list

# 🚀 One-command setup for new developers
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🤖 Setting up COMPUTRON_9000 development environment..."
    
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        echo "❌ uv is not installed. Please install it first:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    
    # Check if podman is installed
    if ! command -v podman &> /dev/null; then
        echo "⚠️  Podman is not installed. Some features may not work."
        echo "   Install from: https://podman.io/getting-started/installation"
    fi
    
    # Create virtual environment
    echo "📦 Creating virtual environment..."
    uv venv .venv
    
    # Install dependencies
    echo "📚 Installing dependencies..."
    uv pip install -e .
    uv pip install -e .[test]
    uv pip install -e .[dev]
    
    # Check if Ollama is running
    echo "🧠 Checking Ollama status..."
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "⚠️  Ollama doesn't appear to be running at http://localhost:11434"
        echo "   Please install and start Ollama: https://ollama.com/"
    else
        echo "✅ Ollama is running!"
    fi
    
    # Run a quick test
    echo "🧪 Running quick health check..."
    uv run python -c "import agents, tools, utils; print('✅ All imports successful!')"
    
    echo ""
    echo "🎉 Setup complete! You can now:"
    echo "   • Run the app: just run"
    echo "   • Run tests: just test"
    echo "   • See all commands: just"

# Run the main application
run:
    uv run main.py

# Run the application in development mode with auto-reload
dev:
    uv run python main.py --dev

# Start the server with hot reload (if implemented)
serve:
    uv run python main.py

# 📦 Dependency management
# Add a new dependency to the project
add package:
    uv add {{package}}

# Add a development dependency
add-dev package:
    uv add --dev {{package}}

# Remove a dependency from the project
remove package:
    uv remove {{package}}
    
# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# Sync dependencies (useful after pulling changes)
sync:
    uv pip sync

# Show dependency tree
tree:
    uv tree

# Check for security vulnerabilities
security-check:
    uv pip audit

# 🧪 Testing commands
# Run all tests with coverage
test:
    PYTHONPATH=. uv run pytest

# Run tests with coverage report
test-cov:
    PYTHONPATH=. uv run pytest --cov-report=html --cov-report=term

# Run only unit tests
test-unit:
    PYTHONPATH=. uv run pytest -m unit

# Run only integration tests  
test-integration:
    PYTHONPATH=. uv run pytest -m integration

# Run tests for a specific file or pattern
test-file file:
    PYTHONPATH=. uv run pytest {{file}}

# Run tests in watch mode (requires pytest-watch)
test-watch:
    PYTHONPATH=. uv run ptw

# Run tests with verbose output
test-verbose:
    PYTHONPATH=. uv run pytest -v

# Run quick tests (exclude slow ones)
test-quick:
    PYTHONPATH=. uv run pytest -m "not slow"

# 🔧 Development tools
# Format code with black and ruff (for imports)
format:
    uv run ruff check --select I --fix .
    uv run black .

# Lint code with ruff
lint:
    uv run ruff check .

# Fix linting issues automatically (including import sorting)
lint-fix:
    uv run ruff check --fix .

# Auto-fix everything possible (format + lint fixes)
fix:
    uv run ruff check --fix .
    uv run black .

# Type check with mypy
typecheck:
    uv run mypy .

# Run all quality checks
check: format lint typecheck

# 🧹 Cleanup commands
# Clean Python cache files
clean-cache:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete

# Clean virtual environment
clean-venv:
    rm -rf .venv

# Full clean (cache + venv)
clean: clean-cache clean-venv

# 🔄 Maintenance
# Upgrade all packages to latest compatible versions
upgrade:
    uv pip install --upgrade -e .[test,dev]

# Security audit of dependencies
audit:
    uv pip audit

# Show project info
info:
    @echo "📊 COMPUTRON_9000 Project Info"
    @echo "Python version: $(cat .python-version)"
    @echo "Dependencies:"
    @uv pip list
    @echo ""
    @echo "📁 Project structure:"
    @tree -I '__pycache__|*.pyc|.venv' -L 2
