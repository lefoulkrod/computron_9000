# Justfile for computron_9000 project

# =============================================
# Meta & Help
# =============================================
# Default recipe - show available commands
default:
    @just --list


# =============================================
# � Variables
# =============================================
# Centralize UI directory path to avoid repetition
UI_DIR := "server/ui"


# =============================================
# Setup & Run
# =============================================
# One-command setup for new developers
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
    
    # Check if Node.js is installed
    if ! command -v node &> /dev/null; then
        echo "⚠️  Node.js is not installed. UI development will not work."
        echo "   Install from: https://nodejs.org/ or use nvm/fnm"
    fi
    
    # Check if podman is installed
    if ! command -v podman &> /dev/null; then
        echo "⚠️  Podman is not installed. Some features may not work."
        echo "   Install from: https://podman.io/getting-started/installation"
    fi
    
    # Create virtual environment (idempotent)
    if [ -d ".venv" ]; then
        echo "📦 Python virtual environment already exists at .venv — skipping creation"
    else
        echo "📦 Creating Python virtual environment..."
        uv venv .venv
    fi
    
    # Install Python dependencies
    echo "📚 Installing Python dependencies..."
    uv sync --all-extras

    # Install the project in editable mode so imports work without PYTHONPATH
    echo "🧩 Installing project in editable mode..."
    uv pip install -e .
    
    # Install Playwright browser(s)
    echo "🎭 Ensuring Playwright Chromium is installed..."
    # Don't fail the whole setup if this step has issues (network, permissions)
        if uv run python -c "from pathlib import Path; import sys; driver_dir = Path.home() / '.cache' / 'ms-playwright'; exists = any((driver_dir / 'chromium' / p).exists() for p in ('chromium','chrome-linux')); sys.exit(0 if exists else 1)"; then
        echo "✅ Playwright Chromium already present"
    else
        if uv run playwright install chromium; then
            echo "✅ Playwright Chromium installed"
        else
            echo "⚠️  Playwright browser install failed. You can try manually:"
            echo "   • just playwright-install            # default chromium"
            echo "   • just playwright-install firefox    # firefox"
            echo "   • just playwright-install-all        # all + Linux deps (may require sudo)"
        fi
    fi

    # Enable Podman user API socket if available
    if command -v podman &> /dev/null && command -v systemctl &> /dev/null; then
        echo "🔌 Enabling Podman API socket (user)..."
        if systemctl --user enable --now podman.socket; then
            echo "✅ Podman API socket enabled."
        else
            echo "⚠️  Could not enable Podman user socket automatically."
            echo "   You can enable it later with: just podman-enable-socket"
        fi
    fi
    
    # Install UI dependencies if Node.js is available
    if command -v node &> /dev/null && command -v npm &> /dev/null; then
        echo "🎨 Installing UI dependencies..."
        cd {{UI_DIR}}
        if [ -f "package-lock.json" ]; then
            npm ci
        else
            npm install
        fi
        cd ../..
    fi
    
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
    echo "   • Start UI dev server: just ui-dev"
    echo "   • Build UI: just ui-build"
    echo "   • Run full dev stack: just dev-full"
    echo "   • See all commands: just"

# Run the main application
run:
    uv run main.py

# Run the application in development mode with auto-reload
dev:
    uv run python main.py --dev

# Run backend API and UI dev server concurrently with graceful shutdown
dev-full:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Starting full development stack (backend + UI)"

    # Ensure UI dependencies are installed
    if command -v node &> /dev/null && command -v npm &> /dev/null; then
        if [ ! -d "{{UI_DIR}}/node_modules" ]; then
            echo "📦 Installing UI dependencies..."
            pushd {{UI_DIR}} >/dev/null
            if [ -f "package-lock.json" ]; then
                npm ci
            else
                npm install
            fi
            popd >/dev/null
        fi
    else
        echo "⚠️  Node.js/npm not found. UI dev server will be skipped."
    fi

    # Start backend
    uv run python main.py --dev &
    BACKEND_PID=$!

    # Start UI if tools available
    if command -v node &> /dev/null && command -v npm &> /dev/null; then
        pushd {{UI_DIR}} >/dev/null
        npm run dev &
        UI_PID=$!
        popd >/dev/null
    else
        UI_PID=""
    fi

    cleanup() {
        echo "\n🧹 Shutting down..."
        if [ -n "${UI_PID}" ]; then
            kill ${UI_PID} 2>/dev/null || true
            wait ${UI_PID} 2>/dev/null || true
        fi
        kill ${BACKEND_PID} 2>/dev/null || true
        wait ${BACKEND_PID} 2>/dev/null || true
        echo "✅ All processes stopped"
    }
    trap cleanup INT TERM

    # Wait for background processes
    if [ -n "${UI_PID}" ]; then
        wait ${BACKEND_PID} ${UI_PID}
    else
        wait ${BACKEND_PID}
    fi


# =============================================
# 📦 Dependency Management
# =============================================
# Add a new dependency to the project
add package:
    uv add {{package}}

# Add a development dependency
add-dev package:
    uv add --dev {{package}}

# Remove a dependency from the project
remove package:
    uv remove {{package}}
    
# Sync dependencies (useful after pulling changes)
sync:
    uv sync --all-extras

# List outdated dependencies (top-level only)
outdated:
    uv tree --outdated --depth=1

# Show dependency tree
tree:
    uv tree

# Upgrade all packages to latest compatible versions
upgrade:
    uv sync --upgrade

# Security audit of dependencies
audit:
    uv tool run safety check


# =============================================
# 🧪 Testing
# =============================================
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


# =============================================
# 🔧 Quality, Linting & CI
# =============================================
# Format code with ruff (formatter) and fix imports
format:
    uv run ruff format .
    uv run ruff check --fix .

# Verify formatting without making changes (non-mutating)
format-check:
    uv run ruff format --check .

# Lint code with ruff
lint:
    uv run ruff check .

# Type check with mypy
typecheck:
    uv run mypy .

# Run all quality checks (non-mutating)
check: format-check lint typecheck

# Run all checks including tests (pre-commit/CI style)
ci: check test

# Install pre-commit hooks (requires pre-commit package)
pre-commit-install:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if [ -f ".pre-commit-config.yaml" ]; then
        echo "🪝 Installing pre-commit hooks..."
        uv run pre-commit install
        echo "✅ Pre-commit hooks installed!"
    else
        echo "ℹ️  No .pre-commit-config.yaml found"
        echo "   Consider adding pre-commit configuration for automated checks"
    fi

# Run pre-commit on all files
pre-commit-all:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if [ -f ".pre-commit-config.yaml" ]; then
        echo "🔍 Running pre-commit on all files..."
        uv run pre-commit run --all-files
    else
        echo "ℹ️  No .pre-commit-config.yaml found, running manual checks..."
        just ci
    fi


# =============================================
# 🎨 UI Development
# =============================================
# Install UI dependencies
ui-install:
    #!/usr/bin/env bash
    set -euo pipefail
    
    # Check if Node.js and npm are installed
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed. Please install Node.js first:"
        echo "   https://nodejs.org/ or use nvm/fnm"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed. Please install npm first"
        exit 1
    fi
    
    echo "📦 Installing UI dependencies..."
    cd {{UI_DIR}}
    npm install
    echo "✅ UI dependencies are up to date!"

# Start UI development server
ui-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    
    # Check if Node.js and npm are installed
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed. Please install Node.js first:"
        echo "   https://nodejs.org/ or use nvm/fnm"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed. Please install npm first"
        exit 1
    fi
    
    echo "🚀 Starting UI development server..."
    cd {{UI_DIR}}
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing Node.js dependencies first..."
        if [ -f "package-lock.json" ]; then
            npm ci
        else
            npm install
        fi
    fi
    npm run dev

# Build the React UI for production
ui-build:
    #!/usr/bin/env bash
    set -euo pipefail
    
    # Check if Node.js and npm are installed
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed. Please install Node.js first:"
        echo "   https://nodejs.org/ or use nvm/fnm"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed. Please install npm first"
        exit 1
    fi
    
    echo "🏗️  Building React UI..."
    cd {{UI_DIR}}
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing Node.js dependencies..."
        if [ -f "package-lock.json" ]; then
            npm ci
        else
            npm install
        fi
    fi
    npm run build
    echo "✅ UI build complete!"

# Run UI tests (Vitest)
ui-test *args:
    #!/usr/bin/env bash
    set -euo pipefail

    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed. Please install Node.js first:"
        echo "   https://nodejs.org/ or use nvm/fnm"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed. Please install npm first"
        exit 1
    fi

    echo "🧪 Running UI tests..."
    cd {{UI_DIR}}
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing Node.js dependencies first..."
        if [ -f "package-lock.json" ]; then
            npm ci
        else
            npm install
        fi
    fi

    if [ "$#" -eq 0 ]; then
        npm run test
    else
        npm run test -- "$@"
    fi

# Clean UI artifacts
# Remove only built assets (preserve node_modules by default)
ui-clean-build:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🧹 Cleaning UI build artifacts (dist)..."
    cd {{UI_DIR}}
    rm -rf dist
    echo "✅ UI build artifacts cleaned!"

# Remove UI dependencies (node_modules)
ui-clean-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🧹 Cleaning UI dependencies (node_modules)..."
    cd {{UI_DIR}}
    rm -rf node_modules
    echo "✅ UI dependencies cleaned!"

# Default UI clean preserves node_modules for faster reinstalls
ui-clean: ui-clean-build


# =============================================
# 🧹 Cleanup
# =============================================
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


# =============================================
# 📊 Project Info
# =============================================
# Show project information (Python version, deps, tree)
info:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "📊 COMPUTRON_9000 Project Info"
    if command -v uv >/dev/null 2>&1; then
        echo "Python version: $(uv run python -V)"
    elif command -v python >/dev/null 2>&1; then
        echo "Python version: $(python -V)"
    else
        echo "Python version: (python not found)"
    fi
    echo "Dependencies:"
    if command -v uv >/dev/null 2>&1; then
        uv tree --depth=1
    else
        echo "(uv not found) Skipping dependency tree"
    fi
    echo ""
    echo "📁 Project structure:"
    if command -v tree >/dev/null 2>&1; then
        tree -I '__pycache__|*.pyc|.venv' -L 2
    else
        echo "(tree not installed) Skipping directory tree. Install 'tree' for a nicer view."
    fi


# =============================================
# 🐳 Containers (Podman)
# =============================================
# Build Podman image 'computron_9000:latest'
container-build:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if ! command -v podman &> /dev/null; then
        echo "❌ Podman is not installed. Please install it first:"
        echo "   https://podman.io/getting-started/installation"
        exit 1
    fi
    
    echo "🏗️  Building container image..."
    podman build --format docker -f computron_os_dockerfile -t computron_9000:latest .
    echo "✅ Container image built successfully!"

# Start 'computron_virtual_computer' container (create volumes)
container-start:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if ! command -v podman &> /dev/null; then
        echo "❌ Podman is not installed. Please install it first:"
        echo "   https://podman.io/getting-started/installation"
        exit 1
    fi
    
    if ! [ -f "config.yaml" ]; then
        echo "❌ config.yaml not found. Please ensure you're in the project root."
        exit 1
    fi
    
    if ! podman image exists computron_9000:latest; then
        echo "❌ Container image not found. Building first..."
        just container-build
    fi
    
    if podman container exists computron_virtual_computer; then
        if [ "$(podman container inspect computron_virtual_computer --format '{{{{.State.Status}}}}')" = "running" ]; then
            echo "ℹ️  Container 'computron_virtual_computer' is already running"
            exit 0
        else
            echo "🗑️  Removing stopped container..."
            podman rm computron_virtual_computer
        fi
    fi
    
    echo "🚀 Starting container..."
    home_dir=$(awk '/^virtual_computer:/ {found=1} found && /home_dir:/ {print $2; exit}' config.yaml)
    if [ ! -d "$home_dir" ]; then 
        echo "📁 Creating home directory: $home_dir"
        mkdir -p "$home_dir"
    fi
    
    podman run -d --rm \
      --name computron_virtual_computer \
      --userns=keep-id \
      --group-add keep-groups \
      -v "$home_dir:/home/computron:rw,z" \
      computron_9000:latest sleep infinity
      
    echo "✅ Container 'computron_virtual_computer' started successfully!"

# Stop 'computron_virtual_computer' container
container-stop:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if ! command -v podman &> /dev/null; then
        echo "❌ Podman is not installed"
        exit 1
    fi
    
    if podman container exists computron_virtual_computer; then
        echo "🛑 Stopping container..."
        podman stop computron_virtual_computer
        echo "✅ Container stopped"
    else
        echo "ℹ️  Container 'computron_virtual_computer' is not running"
    fi

# Open interactive shell in container
container-shell:
    #!/usr/bin/env bash
    set -euo pipefail
    
    if ! command -v podman &> /dev/null; then
        echo "❌ Podman is not installed"
        exit 1
    fi
    
    if podman container exists computron_virtual_computer; then
        if [ -n "$(podman ps -q --filter name=^computron_virtual_computer$ --filter status=running)" ]; then
            echo "🐚 Opening shell in container..."
            podman exec -it computron_virtual_computer bash
        else
            echo "❌ Container 'computron_virtual_computer' exists but is not running"
            echo "   Start it with: just container-start"
            exit 1
        fi
    else
        echo "❌ Container 'computron_virtual_computer' does not exist"
        echo "   Start it with: just container-start"
        exit 1
    fi

# Get container status and info
container-status:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v podman &> /dev/null; then
        echo "❌ Podman is not installed"
        exit 1
    fi
    
    echo "📊 Container Status:"
    if podman container exists computron_virtual_computer; then
        echo "   Name: computron_virtual_computer"
        if [ -n "$(podman ps -q --filter name=^computron_virtual_computer$ --filter status=running)" ]; then
            echo "   Status: running"
            echo "   ✅ Container is running and ready"
            echo "   🐚 Access with: just container-shell"
        else
            # Fallback: extract status from JSON (avoids Go templates in shell)
            status=$(podman container inspect computron_virtual_computer | grep -m1 '"Status"' | sed -E 's/.*"Status"\s*:\s*"([^"]+)".*/\1/')
            status=${status:-unknown}
            echo "   Status: $status"
            echo "   ⚠️  Container exists but is not running"
            echo "   🚀 Start with: just container-start"
        fi
    else
        echo "   ❌ Container does not exist"
        echo "   🚀 Create and start with: just container-start"
    fi

# Podman helpers
# Enable and start the Podman API socket for the current user
podman-enable-socket:
    @echo "Enabling Podman API socket (user)..."
    systemctl --user enable --now podman.socket
    @echo "✅ Podman API socket enabled."
    @echo "Tip: For Docker-compatible clients, set:"
    @echo "     export DOCKER_HOST=unix:///run/user/$$(id -u)/podman/podman.sock"


# =============================================
# 🎭 Playwright
# =============================================
# Install Playwright browser (default: chromium)
playwright-install browser='chromium':
    uv run playwright install {{browser}}

# Install all Playwright browsers + Linux system deps
playwright-install-all:
    uv run playwright install --with-deps
