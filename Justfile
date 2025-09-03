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
    uv sync --all-extras
    
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
    uv sync --all-extras

# Show dependency tree
tree:
    uv tree

# 🕹 Playwright helpers

# Install only specific browser engines (chromium, firefox, webkit)
playwright-install-browser browser:
    uv run python -m playwright install {{browser}}

# Install Playwright system dependencies (Linux)
playwright-install-deps:
    @set -euo pipefail; \
    if command -v apt-get >/dev/null 2>&1; then \
        echo "Installing Playwright system deps via apt-get..."; \
        sudo apt-get update; \
        sudo apt-get install -y \
            libnss3 \
            libnspr4 \
            libdbus-1-3 \
            libatk1.0-0 \
            libatk-bridge2.0-0 \
            libcups2 \
            libxcb1 \
            libatspi2.0-0 \
            libx11-6 \
            libxcomposite1 \
            libxdamage1 \
            libxext6 \
            libxfixes3 \
            libxrandr2 \
            libgbm1 \
            libpango-1.0-0 \
            libcairo2 \
            libasound2; \
    elif command -v dnf >/dev/null 2>&1; then \
        echo "Installing Playwright system deps via dnf..."; \
        sudo dnf install -y \
            nss \
            nspr \
            dbus-libs \
            atk \
            at-spi2-atk \
            cups-libs \
            libxcb \
            at-spi2-core \
            libX11 \
            libXcomposite \
            libXdamage \
            libXext \
            libXfixes \
            libXrandr \
            mesa-libgbm \
            pango \
            cairo \
            alsa-lib; \
    elif command -v yum >/dev/null 2>&1; then \
        echo "Installing Playwright system deps via yum..."; \
        sudo yum install -y \
            nss \
            nspr \
            dbus-libs \
            atk \
            at-spi2-atk \
            cups-libs \
            libxcb \
            at-spi2-core \
            libX11 \
            libXcomposite \
            libXdamage \
            libXext \
            libXfixes \
            libXrandr \
            mesa-libgbm \
            pango \
            cairo \
            alsa-lib; \
    elif command -v zypper >/dev/null 2>&1; then \
        echo "Installing Playwright system deps via zypper..."; \
        sudo zypper install -y \
            mozilla-nss \
            mozilla-nspr \
            libdbus-1-3 \
            atk \
            at-spi2-atk \
            libcups2 \
            libxcb1 \
            at-spi2-core \
            libX11-6 \
            libXcomposite1 \
            libXdamage1 \
            libXext6 \
            libXfixes3 \
            libXrandr2 \
            libgbm1 \
            pango \
            cairo \
            alsa; \
    else \
        echo "Unsupported package manager. Please install system packages manually." >&2; \
        exit 1; \
    fi

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
    uv run ruff format .
    uv run ruff check --fix .

# Lint code with ruff
lint:
    uv run ruff check .

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
    uv sync --upgrade

# Security audit of dependencies
audit:
    uv tool run safety check

# Show project info
info:
    @echo "📊 COMPUTRON_9000 Project Info"
    @echo "Python version: $(cat .python-version)"
    @echo "Dependencies:"
    @uv tree --depth=1
    @echo ""
    @echo "📁 Project structure:"
    @tree -I '__pycache__|*.pyc|.venv' -L 2


# � Container commands
container-build:
    podman build --format docker -f computron_os_dockerfile -t computron_9000:latest .

container-stop:
    podman stop computron_virtual_computer

container-start:
    @home_dir=$(awk '/^virtual_computer:/ {found=1} found && /home_dir:/ {print $2; exit}' config.yaml); \
    if [ ! -d "$home_dir" ]; then mkdir -p "$home_dir"; fi; \
    podman run -d --rm \
      --name computron_virtual_computer \
      --userns=keep-id \
      --group-add keep-groups \
      -v "$home_dir:/home/computron:rw,z" \
      computron_9000:latest sleep infinity
    @echo "Container 'computron_virtual_computer' started in background and ready for exec commands."

container-shell:
    @if podman container exists computron_virtual_computer; then \
        echo "Opening shell in running container computron_virtual_computer"; \
        podman exec -it computron_virtual_computer bash; \
    else \
        echo "Container 'computron_virtual_computer' is not running. Start it with: just container-start" >&2; \
        exit 1; \
    fi


# 🐳 Podman helpers
# Enable and start the Podman API socket for the current user
podman-enable-socket:
    @echo "Enabling Podman API socket (user)..."
    systemctl --user enable --now podman.socket
    @echo "✅ Podman API socket enabled."
    @echo "Tip: For Docker-compatible clients, set:"
    @echo "     export DOCKER_HOST=unix:///run/user/$$(id -u)/podman/podman.sock"

