# COMPUTRON_9000

COMPUTRON_9000 is a modern, extensible AI assistant platform with a responsive chat UI, Python backend, and easy local setup.

![COMPUTRON_9000 Logo](image.png)

## Features
- Modern, responsive chat UI (ChatGPT style)
- System prompt for consistent assistant behavior
- Python proxy server for CORS and API routing
- Easy setup with [uv](https://github.com/astral-sh/uv) and `pyproject.toml`
- Multiple agent SDKs (ollama, adk, pydantic)
- **Playwright test execution tool**: Run Playwright test scripts in a containerized Node.js environment using Podman
- Tool integration for web browsing, code execution, and more

## Requirements
- Python 3.11.12 (see `.python-version`)
- [uv](https://github.com/astral-sh/uv) (for dependency and venv management)
- [Ollama](https://ollama.com/) running locally (default: `http://localhost:11434`)
- [Podman](https://podman.io/) installed and running as a user service
- [Just](https://github.com/casey/just) command runner (optional but recommended)

## Quick Start

The fastest way to get started is using the `just` command runner:

```sh
# Clone the repository
git clone https://github.com/lefoulkrod/computron_9000.git
cd computron_9000

# Install dependencies
just install-all

# Start Ollama (if not already running)
./start_ollama.sh

# Run the application with ollama agent SDK
just run-ollama
```

Then visit [http://localhost:8080](http://localhost:8080) in your browser.

## Detailed Setup

1. **Clone the repo:**
   ```sh
   git clone https://github.com/lefoulkrod/computron_9000.git
   cd computron_9000
   ```

2. **Create a virtual environment:**
   ```sh
   uv venv .venv
   ```

3. **Activate the virtual environment:**
   - On Unix/macOS:
     ```sh
     source .venv/bin/activate
     ```
   - On Windows:
     ```sh
     .venv\Scripts\activate
     ```

4. **Enable Podman systemd socket (required for code execution tools):**
   ```sh
   systemctl --user enable --now podman.socket
   ```

5. **Install dependencies:**
   ```sh
   uv pip install -r pyproject.toml
   ```

6. **Start Ollama (if not already running):**
   ```sh
   ./start_ollama.sh
   ```

7. **Start the application:**
   ```sh
   # Using the default agent SDK
   uv run main.py
   
   # Or specify an agent SDK
   AGENT_SDK=ollama uv run main.py
   ```

8. **Open the chat UI:**
   - Visit [http://localhost:8080](http://localhost:8080) in your browser

## Project Structure

- `agents/`: Agent implementations and SDKs
  - `ollama/`: Ollama-based agent implementations
  - `adk/`: ADK agent implementations
- `tools/`: Tool implementations for agents
  - `code/`: Code execution tools
  - `fs/`: Filesystem tools
  - `web/`: Web browsing and search tools
  - `misc/`: Miscellaneous tools
- `server/`: Web server implementation
- `models/`: Model configuration
- `tests/`: Test suite

## Available Commands

COMPUTRON_9000 uses [Just](https://github.com/casey/just) for common tasks. See the `Justfile` for all commands or run `just --list`.

Key commands:
```
just run-ollama     # Run with ollama agent SDK
just run-adk        # Run with adk agent SDK
just test           # Run all tests
just install-all    # Install all dependencies
```

## Configuration

The application can be configured using `config.yaml` in the root directory.

## Usage
- Type your message and press Enter or click Send in the web UI
- Use the available tools through agent interactions
- Customize system prompts in the `agents/prompt.py` file

## Troubleshooting

1. **Ollama issues**: Ensure Ollama is running with `./start_ollama.sh`
2. **Podman errors**: Make sure podman socket is enabled with `systemctl --user status podman.socket`
3. **Import errors**: Verify dependencies are installed with `just install-all`

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Install development dependencies (`just install-all`)
4. Make your changes and add tests
5. Run tests to ensure they pass (`just test`)
6. Commit your changes
7. Push to your branch
8. Open a Pull Request



