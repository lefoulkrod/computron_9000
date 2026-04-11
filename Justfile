# Justfile for computron_9000 project

set dotenv-load

# =============================================
# Meta & Help
# =============================================
# Default recipe - show available commands
default:
    @just --list


# =============================================
# 📦 Variables
# =============================================
# Centralize UI directory path to avoid repetition
UI_DIR := "server/ui"


# =============================================
# Setup & Run
# =============================================
# One-command setup for new developers
setup home_dir=`echo "$HOME/.computron_9000"`:
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
    
    # Create app home directory structure
    echo "🔧 Creating home directories..."
    mkdir -p "{{home_dir}}/custom_tools/scripts"
    echo "✅ Directories ready at {{home_dir}}"

    # Install Playwright browsers for e2e tests
    echo "🎭 Installing Playwright browsers..."
    uv run playwright install chromium

    # Run a quick test
    echo "🧪 Running quick health check..."
    uv run python -c "import agents, tools, utils; print('✅ All imports successful!')"
    
    echo ""
    echo "🎉 Setup complete! You can now:"
    echo "   • Build container:  just container-build"
    echo "   • Test in container: just container-test"
    echo "   • Dev container:    just container-dev"
    echo "   • Run tests: just test"
    echo "   • Run e2e tests: just e2e"
    echo "   • See all commands: just"



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

# Install Playwright browsers (one-time setup)
e2e-install:
    uv run playwright install chromium

# Run e2e tests — starts a throwaway container on :9090, runs tests, stops it
e2e *args:
    #!/usr/bin/env bash
    set -euo pipefail
    port=9090
    name="computron_e2e"
    docker image inspect computron_9000:latest &>/dev/null || just container-build
    just container-build-ui
    docker rm -f "$name" 2>/dev/null || true
    env_args=""; [ -f .env ] && env_args="--env-file .env"
    docker run -d --rm --name "$name" \
      --gpus all --shm-size=256m --network=host \
      -e PORT=$port \
      $env_args \
      -v "$(pwd):/opt/computron:rw" \
      computron_9000:latest \
      bash -c "cd /opt/computron && exec python3.12 main.py"
    # Wait for app server
    ready=false
    for i in $(seq 1 30); do
      if curl -s "http://localhost:$port/api/settings" >/dev/null 2>&1; then
        ready=true; break
      fi
      sleep 2
    done
    if [ "$ready" = false ]; then
      echo "❌ App server did not start on :$port"
      docker logs "$name" 2>&1 | tail -20
      docker stop "$name" 2>/dev/null || true
      exit 1
    fi
    # Run tests, capture exit code
    rc=0
    COMPUTRON_URL="http://localhost:$port" PYTHONPATH=. uv run pytest e2e/ "$@" || rc=$?
    docker stop "$name" 2>/dev/null || true
    exit $rc


# =============================================
# 🔧 Quality, Linting & CI
# =============================================
# Format code with ruff (formatter) and fix imports
format:
    uv run ruff check --fix .
    uv run ruff format .

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
# Run the linter before the formatter-check so diagnostics are visible even
# when the formatter would otherwise report files that *would* be reformatted.
check: lint typecheck format-check

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
# 📊 Evaluation Tools
# =============================================
# Start the compaction evaluation web app
eval port='8081':
    PYTHONPATH=. PORT={{port}} uv run python -m tools.compaction_eval.app


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
# 🐳 Containers (Docker)
# =============================================

_ctr_name := "computron_virtual_computer"

# Build the container image
container-build:
    echo "🏗️  Building container image..."
    docker build -f container/Dockerfile -t computron_9000:latest .

# Build UI inside a throwaway container (fixes root-owned dist files)
container-build-ui:
    docker run --rm -v "$(pwd):/opt/computron:rw" computron_9000:latest \
      bash -c "cd /opt/computron/server/ui && npm run build"

# Run a throwaway container with latest source — builds UI, no persistent state
container-test:
    #!/usr/bin/env bash
    set -euo pipefail
    docker image inspect computron_9000:latest &>/dev/null || just container-build
    just container-build-ui
    env_args=""; [ -f .env ] && env_args="--env-file .env"
    echo "🚀 Throwaway container (ctrl+c to discard)"
    docker run --rm -it \
      --gpus all --shm-size=256m --network=host \
      $env_args \
      -v "$(pwd):/opt/computron:rw" \
      computron_9000:latest

# Start container for regular use (named volumes for persistent state)
container-start:
    #!/usr/bin/env bash
    set -euo pipefail
    docker image inspect computron_9000:latest &>/dev/null || just container-build
    if docker ps -q --filter name=^{{_ctr_name}}$ 2>/dev/null | grep -q .; then
        echo "ℹ️  Already running"; exit 0
    fi
    docker rm -f {{_ctr_name}} 2>/dev/null || true
    env_args=""; [ -f .env ] && env_args="--env-file .env"
    docker run -d --rm \
      --name {{_ctr_name}} \
      --gpus all --shm-size=256m --network=host \
      $env_args \
      -v computron_home:/home/computron:rw \
      -v computron_state:/var/lib/computron:rw \
      computron_9000:latest
    echo "✅ Started"

# Start container for development (source + state mounted to host)
container-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    docker image inspect computron_9000:latest &>/dev/null || just container-build
    if docker ps -q --filter name=^{{_ctr_name}}$ 2>/dev/null | grep -q .; then
        echo "ℹ️  Already running"; exit 0
    fi
    docker rm -f {{_ctr_name}} 2>/dev/null || true
    env_args=""; [ -f .env ] && env_args="--env-file .env"
    state_dir="$HOME/.computron_9000"
    mkdir -p "$state_dir/state" "$state_dir/home"
    docker run -d --rm \
      --name {{_ctr_name}} \
      --gpus all --shm-size=256m --network=host \
      -e PYTHONDONTWRITEBYTECODE=1 \
      $env_args \
      -v "$state_dir/home:/home/computron:rw" \
      -v "$state_dir/state:/var/lib/computron:rw" \
      -v "$(pwd):/opt/computron:rw" \
      computron_9000:latest
    echo "✅ Dev container started (source mounted, state at $state_dir/)"

# Rebuild React UI inside the running container
container-rebuild-ui:
    docker exec {{_ctr_name}} bash -c "cd /opt/computron/server/ui && npm run build"

# Restart app + inference servers (desktop/VNC stay up)
container-restart-app:
    docker exec {{_ctr_name}} pkill -9 -f "inference_server.py" 2>/dev/null || true
    docker exec {{_ctr_name}} rm -f /tmp/inference_server.pid 2>/dev/null || true
    docker exec {{_ctr_name}} pkill -f "python3.12 main.py" 2>/dev/null || true
    echo "✅ Servers restarting"

# Stop the container
container-stop:
    docker stop {{_ctr_name}} 2>/dev/null || echo "ℹ️  Not running"

# Open a shell in the running container
container-shell:
    docker exec -it {{_ctr_name}} bash

# Follow app server logs
container-logs:
    docker logs -f {{_ctr_name}}

# Follow inference server logs
container-inference-logs:
    docker exec {{_ctr_name}} tail -f /tmp/inference_server.log

# Publish image to GitHub Container Registry
publish registry="ghcr.io/lefoulkrod/computron_9000":
    #!/usr/bin/env bash
    set -euo pipefail
    docker image inspect computron_9000:latest &>/dev/null || { echo "❌ No image. Run: just container-build"; exit 1; }
    sha=$(git rev-parse --short HEAD)
    branch=$(git branch --show-current | tr '/' '-')
    tag="${branch}-${sha}"
    echo "🏷️  Tagging as {{registry}}:${tag} and {{registry}}:${branch}-latest"
    docker tag computron_9000:latest "{{registry}}:${tag}"
    docker tag computron_9000:latest "{{registry}}:${branch}-latest"
    [ -n "${GITHUB_PACKAGES_TOKEN:-}" ] && echo "$GITHUB_PACKAGES_TOKEN" | docker login ghcr.io -u lefoulkrod --password-stdin 2>/dev/null
    docker push "{{registry}}:${tag}"
    docker push "{{registry}}:${branch}-latest"
    echo "✅ Published: {{registry}}:${tag}"

# View both app + inference logs side by side
logs:
    #!/usr/bin/env bash
    set -euo pipefail
    docker logs -f computron_virtual_computer 2>&1 | sed 's/^/[app] /' &
    docker exec computron_virtual_computer tail -f /tmp/inference_server.log 2>/dev/null | sed 's/^/[inference] /' &
    wait

