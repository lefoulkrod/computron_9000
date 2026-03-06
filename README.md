# COMPUTRON_9000

COMPUTRON_9000 is an AI assistant that runs on your own hardware. It currently uses Ollama as its inference provider. I run it on 84GB VRAM across 4 GPUs.

![COMPUTRON_9000 Logo](image.png)

## Features
- Modern, responsive chat UI
- Multiple agents to attend to your needs
- Using its various agents COMPUTRON can:
  1. Write and execute Python code
  2. Search the web (Google, Reddit)
  3. Perform research and summarize findings
  4. Execute bash commands inside a container
  5. Interact with a browser (automation & scraping)
  6. Create, save, and reuse custom tools it writes itself (persisted across restarts)
  7. Remember facts and preferences across sessions with persistent memory
  8. Generate images (Flux.1-schnell), videos (Wan2.1-T2V-1.3B), and audio (Kokoro TTS) with GPU acceleration

## Virtual Computer

COMPUTRON_9000 can spin up a Podman container to give agents a sandboxed "virtual computer." This environment shares a volume with the host so files written by agents are accessible outside the container.

Common container commands:

```
just container-build    # build the container image
just container-start    # start the sandbox
just container-shell    # open a shell in the container
just container-stop     # stop the container
just container-status   # view container status
```

## Custom Tools

COMPUTRON_9000 can create its own persistent tools at runtime using `create_custom_tool`, `lookup_custom_tools`, and `run_custom_tool`. Tools are stored in:

- `~/.computron_9000/custom_tools/registry.json` — tool definitions
- `~/.computron_9000/container_home/custom_tools/scripts/` — scripts for program-type tools (visible inside the container at `/home/computron/custom_tools/scripts/`)

These directories are created automatically by `just setup`. If you're setting up manually:

```sh
mkdir -p ~/.computron_9000/custom_tools
mkdir -p ~/.computron_9000/container_home/custom_tools/scripts
```

## Requirements
- Python 3.12+ (see `.python-version`)
- [uv](https://github.com/astral-sh/uv) (for dependency and venv management)
- [Ollama](https://ollama.com/) running locally (default: `http://localhost:11434`)
- [Podman](https://podman.io/) (optional, for the virtual computer)
- [Node.js](https://nodejs.org/) & npm (optional, for UI development)
- [Just](https://just.systems/) (for task automation)

## Quick Start

```sh
git clone computron_9000
cd computron_9000
just setup              # create venv, install deps, run health checks
just setup /custom/dir  # same, with a custom app home directory
just run          # start backend on http://localhost:8080
```

Helpful development commands:

```
just dev          # backend with auto-reload
just dev-full     # backend + React UI
just ui-dev       # UI dev server only
just test         # run test suite
just format       # format code
just lint         # lint with ruff
just typecheck    # type check with mypy
```

Run `just` to see all available tasks. Podman setup requires manual configuration (see Manual Setup below).

## Environment Configuration

Some integrations require additional credentials. Copy `.env.example` to `.env` and populate the following variables when you want to enable the related tools:

- **Reddit tools**: set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` to the values from your Reddit app. These credentials allow the Reddit integration to authenticate with the API.
- **Google search tools**: set `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` (from your Programmable Search Engine) so the Google search utility can make authenticated requests.
- **HuggingFace (GPU media generation)**: set `HF_TOKEN` to enable image and video generation with gated models like Flux.1-schnell. See [GPU Media Generation](#gpu-media-generation) below.

Restart the backend after updating environment variables so the changes take effect.

## GPU Media Generation

COMPUTRON_9000 can generate images, videos, and audio using GPU-accelerated models inside the container. This requires an NVIDIA GPU with at least 12 GB VRAM and a HuggingFace account.

### Models Used
- **Images**: [Flux.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) — 1024x1024, 4 inference steps, state-of-the-art quality
- **Video**: [Wan2.1-T2V-1.3B](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers) — 480p/720p text-to-video
- **Voice/TTS**: [Kokoro-82M](https://github.com/thewh1teagle/kokoro-onnx) — lightweight TTS (pre-cached in the container)

### HuggingFace Token Setup

Flux.1-schnell is a **gated model** — you need a HuggingFace token and must accept the model license before first use.

1. **Create a HuggingFace account** at [huggingface.co](https://huggingface.co)

2. **Accept the Flux.1-schnell license** by visiting the [model page](https://huggingface.co/black-forest-labs/FLUX.1-schnell) and clicking "Agree and access repository"

3. **Generate an access token** at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (a "Read" token is sufficient)

4. **Add the token to your `.env` file**:
   ```sh
   HF_TOKEN=hf_your_token_here
   ```

5. **Rebuild and restart the container**:
   ```sh
   just container-build
   just container-start    # automatically passes HF_TOKEN to the container
   ```

The token is passed to the container as an environment variable via `just container-start`. Model weights are downloaded on first use and cached in the container's persistent home directory (`~/.computron_9000/container_home/`), so subsequent runs skip the download.

### Persistent Inference Server

To avoid reloading ~12 GB of model weights on every generation call, a persistent inference server runs inside the container. It:
- Auto-starts on the first image/video generation request
- Keeps the active model loaded in VRAM for instant subsequent calls
- Auto-shuts down after 10 minutes of inactivity to free VRAM for other workloads (e.g. Ollama)
- Handles model switching (image ↔ video) automatically

## Download Models
```
ollama pull gpt-oss:120b
ollama pull qwen2.5vl:32b
```

## Manual Setup

If you prefer to set up manually or don't have Just installed:

### Prerequisites

- **Python 3.12+** (see `.python-version`)
- **[uv](https://github.com/astral-sh/uv)** (for dependency and venv management)
- **[Ollama](https://ollama.com/)** running locally (default: `http://localhost:11434`)
- **[Podman](https://podman.io/)** (optional, for containerized features)
- **[Node.js](https://nodejs.org/)** & npm (optional, for UI development)
- **[Just](https://just.systems/)** (for task automation)

### Installation Steps

1. **Install uv (if not already installed):**
   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone the repo:**
   ```sh
   git clone computron_9000
   cd computron_9000
   ```

3. **Create a virtual environment:**
   ```sh
   uv venv .venv
   ```

4. **Activate the virtual environment:**
   ```sh
   source .venv/bin/activate
   ```

5. **Install dependencies:**
   ```sh
   uv pip install -e .
   uv pip install -e .[test]
   uv pip install -e .[dev]
   ```

6. **Configure Podman (if using containerized features):**
   ```sh
   # Enable Podman systemd socket for container operations
   systemctl --user enable --now podman.socket
   ```

7. **Download the models:**
   ```
   ollama pull gpt-oss:120b
   ollama pull qwen2.5vl:32b
   ```

8. **Start the application:**
   ```sh
   uv run main.py
   ```

9. **Open the chat UI:**
   - Visit [http://localhost:8080](http://localhost:8080) in your browser.

## Usage
- Type your message and press Enter or click Send.

## Development Commands

This project uses [Just](https://just.systems/) for task running. Helpful recipes include:

```
just format       # format code with ruff
just lint         # lint the code
just typecheck    # mypy type checks
just test         # run tests
just check        # run format-check, lint and typecheck
just ci           # run all checks including tests
just ui-build     # build the React UI for production
```

Run `just --list` to see the full set of available commands.

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.



