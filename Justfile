# Justfile for computron_9000
#
# Dev model:
#   - `just build` builds the container image from the current source.
#     Rebuild only when container/Dockerfile or baked-in deps change.
#   - `just dev` starts a long-running dev container, syncs source into it,
#     builds the UI, and launches the app. State lives at ~/.computron_9000/.
#   - `just restart-app` / `just rebuild-ui` sync the latest source and
#     bounce the relevant bit. No bind mount on /opt/computron — the
#     container can't write into your repo.
#   - `just e2e` spawns a throwaway container on :9090 with ephemeral state,
#     syncs source, builds UI, runs playwright, tears down.

set dotenv-load

UI_DIR  := "server/ui"
_ctr    := "computron_virtual_computer"
_image  := "computron_9000:latest"

# Default — show available commands
default:
    @just --list


# =============================================================================
# Setup & deps
# =============================================================================

# One-command setup for new developers (host-side deps only).
setup home_dir=`echo "$HOME/.computron_9000"`:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🤖 Setting up COMPUTRON_9000..."

    command -v uv >/dev/null || { echo "❌ Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
    command -v node >/dev/null || echo "⚠️  Node.js not installed — UI work will not work locally"

    [ -d .venv ] && echo "📦 .venv exists — skipping" || uv venv .venv
    echo "📚 Installing Python deps..."
    uv sync --all-extras
    uv pip install -e .

    if command -v node >/dev/null && command -v npm >/dev/null; then
        echo "🎨 Installing UI deps..."
        (cd {{UI_DIR}} && ([ -f package-lock.json ] && npm ci || npm install))
    fi

    echo "🎭 Installing Playwright browsers..."
    uv run playwright install chromium

    mkdir -p "{{home_dir}}/home" "{{home_dir}}/state"

    uv run python -c "import agents, tools, utils; print('✅ Imports OK')"
    echo ""
    echo "🎉 Ready. Build the image:  just build"
    echo "   Then start developing:   just dev"

# Re-sync Python deps after pulling or editing pyproject.toml
sync:
    uv sync --all-extras

# Add a runtime dependency
add package:
    uv add {{package}}

# Add a dev dependency
add-dev package:
    uv add --dev {{package}}

# Remove a dependency
remove package:
    uv remove {{package}}


# =============================================================================
# Container image
# =============================================================================

# Build the container image. Only needed when container/Dockerfile changes.
build:
    @echo "🏗️  Building {{_image}}..."
    docker build -f container/Dockerfile -t {{_image}} .

# Publish image to GitHub Container Registry
publish registry="ghcr.io/lefoulkrod/computron_9000":
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-image
    sha=$(git rev-parse --short HEAD)
    branch=$(git branch --show-current | tr '/' '-')
    tag="${branch}-${sha}"
    echo "🏷️  Tagging as {{registry}}:${tag} and {{registry}}:${branch}-latest"
    docker tag {{_image}} "{{registry}}:${tag}"
    docker tag {{_image}} "{{registry}}:${branch}-latest"
    [ -n "${GITHUB_PACKAGES_TOKEN:-}" ] && echo "$GITHUB_PACKAGES_TOKEN" | docker login ghcr.io -u lefoulkrod --password-stdin
    docker push "{{registry}}:${tag}"
    docker push "{{registry}}:${branch}-latest"
    if [ "$branch" = "main" ]; then
        docker tag {{_image}} "{{registry}}:latest"
        docker push "{{registry}}:latest"
    fi
    echo "✅ Published: {{registry}}:${tag}"


# =============================================================================
# Dev loop
# =============================================================================

# Start dev container, sync source, build UI, launch app on :8080 (idempotent)
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-image
    state="$HOME/.computron_9000"
    mkdir -p "$state/home" "$state/state"
    if ! docker ps -q -f name=^{{_ctr}}$ 2>/dev/null | grep -q .; then
        docker rm -f {{_ctr}} 2>/dev/null || true
        env_args=""; [ -f .env ] && env_args="--env-file .env"
        docker run -d --rm --name {{_ctr}} \
            --gpus all --shm-size=256m --network=host \
            -e PYTHONDONTWRITEBYTECODE=1 \
            $env_args \
            -v "$state/home:/home/computron:rw" \
            -v "$state/state:/var/lib/computron:rw" \
            {{_image}}
        echo "🚀 Container started"
    else
        echo "ℹ️  Container already running"
    fi
    just _sync-src {{_ctr}}
    just _ui-build {{_ctr}}
    docker exec {{_ctr}} pkill -f "python3.12 main.py" 2>/dev/null || true
    just _wait-ready 8080
    echo "✅ Ready on http://localhost:8080"

# Sync latest Python source, bounce the app (entrypoint loop respawns it)
restart-app:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-running
    just _sync-src {{_ctr}}
    docker exec {{_ctr}} pkill -9 -f "inference_server.py" 2>/dev/null || true
    docker exec {{_ctr}} rm -f /tmp/inference_server.pid 2>/dev/null || true
    docker exec {{_ctr}} pkill -f "python3.12 main.py" 2>/dev/null || true
    just _wait-ready 8080
    echo "✅ App restarted"

# Sync latest UI source and rebuild dist/ inside the container
rebuild-ui:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-running
    just _sync-src {{_ctr}}
    just _ui-build {{_ctr}}
    echo "✅ UI rebuilt — refresh browser"

# Stop the dev container (keeps state in ~/.computron_9000/)
stop:
    docker stop {{_ctr}} 2>/dev/null || echo "ℹ️  Not running"

# Stop container and wipe state — nukes conversations, goals, settings
reset:
    #!/usr/bin/env bash
    set -euo pipefail
    read -rp "⚠️  Wipe ~/.computron_9000/ ? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "cancelled"; exit 0; }
    docker stop {{_ctr}} 2>/dev/null || true
    rm -rf "$HOME/.computron_9000/home" "$HOME/.computron_9000/state"
    mkdir -p "$HOME/.computron_9000/home" "$HOME/.computron_9000/state"
    echo "✅ State wiped"

# Open a bash shell in the running dev container
shell:
    docker exec -it {{_ctr}} bash

# Follow app + inference logs side by side
logs:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-running
    docker logs -f {{_ctr}} 2>&1 | sed 's/^/[app] /' &
    docker exec {{_ctr}} tail -f /tmp/inference_server.log 2>/dev/null | sed 's/^/[inference] /' &
    wait


# =============================================================================
# Testing
# =============================================================================

# Run all unit tests on host
test:
    PYTHONPATH=. uv run pytest

# Run tests matching a specific file or path
test-file file:
    PYTHONPATH=. uv run pytest {{file}}

# Run only tests marked @pytest.mark.unit
test-unit:
    PYTHONPATH=. uv run pytest -m unit

# Coverage report
test-cov:
    PYTHONPATH=. uv run pytest --cov-report=html --cov-report=term

# Watch mode (pytest-watch)
test-watch:
    PYTHONPATH=. uv run ptw

# Run UI tests (Vitest)
test-ui *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{UI_DIR}}
    [ -d node_modules ] || ([ -f package-lock.json ] && npm ci || npm install)
    if [ "$#" -eq 0 ]; then npm run test; else npm run test -- "$@"; fi

# Spin up a throwaway container with fresh state for manual testing on :9090.
# Ctrl-C tears it down. State is ephemeral — nothing persists after exit.
manual-test:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-image
    name="computron_manual_test"
    port=9090
    state=$(mktemp -d)
    mkdir -p "$state/home" "$state/state"
    cleanup() {
        docker exec -u 0 "$name" chown -R "$(id -u):$(id -g)" \
            /home/computron /var/lib/computron 2>/dev/null || true
        docker stop "$name" 2>/dev/null || true
        rm -rf "$state" 2>/dev/null || true
    }
    trap cleanup EXIT

    docker rm -f "$name" 2>/dev/null || true
    env_args=""; [ -f .env ] && env_args="--env-file .env"

    docker run -d --rm --name "$name" \
        --gpus all --shm-size=256m --network=host \
        -e PORT=$port \
        -e DISPLAY=:100 \
        -e ENABLE_DESKTOP=false \
        $env_args \
        -v "$state/home:/home/computron:rw" \
        -v "$state/state:/var/lib/computron:rw" \
        {{_image}}

    just _sync-src "$name"
    docker exec "$name" bash -c "cd /opt/computron/{{UI_DIR}} && npm run build"
    docker exec "$name" pkill -f "python3.12 main.py" 2>/dev/null || true

    ready=false
    for i in $(seq 1 30); do
        if curl -s "http://localhost:$port/api/settings" >/dev/null 2>&1; then
            ready=true; break
        fi
        sleep 2
    done
    if [ "$ready" = false ]; then
        echo "❌ App didn't start on :$port"
        docker logs "$name" 2>&1 | tail -30
        exit 1
    fi

    echo "✅ Ready on http://localhost:$port  (Ctrl-C to tear down)"
    docker logs -f "$name"


# Run Playwright e2e in a throwaway container with fresh state + latest source
e2e *args:
    #!/usr/bin/env bash
    set -euo pipefail
    just _require-image
    name="computron_e2e"
    port=9090
    state=$(mktemp -d)
    mkdir -p "$state/home" "$state/state"
    cleanup() {
        # Chown state files to host uid so we can rm -rf them.
        # Container writes them as computron (uid 1000) or root.
        docker exec -u 0 "$name" chown -R "$(id -u):$(id -g)" \
            /home/computron /var/lib/computron 2>/dev/null || true
        docker stop "$name" 2>/dev/null || true
        rm -rf "$state" 2>/dev/null || true
    }
    trap cleanup EXIT

    docker rm -f "$name" 2>/dev/null || true
    env_args=""; [ -f .env ] && env_args="--env-file .env"

    # --network=host so the container reaches host-local ollama (as :11434).
    # DISPLAY=:100 avoids the abstract X socket clash with a dev container on :99.
    # ENABLE_DESKTOP=false (explicit) skips xfce + VNC + noVNC so ports 5900/6080
    # stay free for a concurrently-running dev container.
    # PORT=$port picks a non-8080 app port so the two aiohttp servers coexist.
    docker run -d --rm --name "$name" \
        --gpus all --shm-size=256m --network=host \
        -e PORT=$port \
        -e DISPLAY=:100 \
        -e ENABLE_DESKTOP=false \
        $env_args \
        -v "$state/home:/home/computron:rw" \
        -v "$state/state:/var/lib/computron:rw" \
        {{_image}}

    just _sync-src "$name"
    docker exec "$name" bash -c "cd /opt/computron/{{UI_DIR}} && npm run build"
    # Bounce main.py so it picks up the synced code + fresh dist
    docker exec "$name" pkill -f "python3.12 main.py" 2>/dev/null || true

    # Wait for the synced app to come up on the e2e port
    ready=false
    for i in $(seq 1 30); do
        if curl -s "http://localhost:$port/api/settings" >/dev/null 2>&1; then
            ready=true; break
        fi
        sleep 2
    done
    if [ "$ready" = false ]; then
        echo "❌ App didn't start on :$port"
        docker logs "$name" 2>&1 | tail -30
        exit 1
    fi

    COMPUTRON_URL="http://localhost:$port" PYTHONPATH=. uv run pytest e2e/ {{args}}


# =============================================================================
# Quality (run on demand)
# =============================================================================

# Lint with ruff
lint:
    uv run ruff check .

# Type check with mypy
typecheck:
    uv run mypy .

# Format (fix imports + format)
format:
    uv run ruff check --fix .
    uv run ruff format .

# Verify formatting without changing files
format-check:
    uv run ruff format --check .

# All non-mutating checks
check: lint typecheck format-check

# CI-style: check + tests
ci: check test


# =============================================================================
# Evaluation tools
# =============================================================================

# Start the compaction evaluation web app
eval port='8081':
    PYTHONPATH=. PORT={{port}} uv run python -m tools.compaction_eval.app


# =============================================================================
# Cleanup
# =============================================================================

# Clean Python caches, .venv, and UI dist (leaves node_modules + state alone)
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
    rm -rf .venv {{UI_DIR}}/dist
    @echo "✅ Cleaned Python caches, .venv, UI dist"


# =============================================================================
# Internal helpers (hidden from --list)
# =============================================================================

# Fail if the image isn't built
_require-image:
    @docker image inspect {{_image}} >/dev/null 2>&1 || { echo "❌ {{_image}} not found. Run: just build"; exit 1; }

# Fail if the dev container isn't running
_require-running:
    @docker ps -q -f name=^{{_ctr}}$ 2>/dev/null | grep -q . || { echo "❌ Container not running. Run: just dev"; exit 1; }

# Tar-pipe working tree into container at /opt/computron.
# Excludes heavy/generated dirs so the stream stays small.
_sync-src ctr:
    @tar \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='.mypy_cache' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        --exclude='{{UI_DIR}}/node_modules' \
        --exclude='{{UI_DIR}}/dist' \
        --exclude='htmlcov' \
        --exclude='.coverage*' \
        --exclude='playwright-report' \
        --exclude='test-results' \
        -cf - . | docker exec -i {{ctr}} tar -xf - -C /opt/computron
    @echo "📦 Source synced into {{ctr}}"

# Install UI deps if package-lock.json has drifted, then build dist/.
# Cheap on steady state (skips install when the lockfile hash matches the
# stamp file inside node_modules). _sync-src excludes node_modules, so
# the image's baked deps persist across syncs — we only reinstall when
# the lockfile actually changed.
_ui-build ctr:
    #!/usr/bin/env bash
    set -euo pipefail
    docker exec {{ctr}} bash -euc '
        cd /opt/computron/{{UI_DIR}}
        lock_hash=$(sha256sum package-lock.json 2>/dev/null | cut -d" " -f1 || echo none)
        stamp=node_modules/.deps-hash
        if [ ! -f "$stamp" ] || [ "$(cat "$stamp" 2>/dev/null)" != "$lock_hash" ]; then
            echo "📦 Syncing UI deps (lockfile changed)..."
            if [ -f package-lock.json ]; then npm ci; else npm install; fi
            echo "$lock_hash" > "$stamp"
        fi
        npm run build
    '

# Poll until the app responds on the given port (up to ~60s)
_wait-ready port:
    #!/usr/bin/env bash
    for i in $(seq 1 30); do
        if curl -s "http://localhost:{{port}}/api/settings" >/dev/null 2>&1; then
            exit 0
        fi
        sleep 2
    done
    echo "⚠️  App didn't respond on :{{port}} within 60s (check 'just logs')"
    exit 1
