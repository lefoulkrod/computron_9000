# COMPUTRON_9000

COMPUTRON_9000 is a modern, extensible AI assistant platform with a responsive chat UI, Python backend, and easy local setup.

![COMPUTRON_9000 Logo](image.png)

## Features
- Modern, responsive chat UI (ChatGPT style)
- System prompt for consistent assistant behavior
- Python proxy server for CORS and API routing
- Easy setup with [uv](https://github.com/astral-sh/uv) and `pyproject.toml`
- **Playwright test execution tool**: Run Playwright test scripts in a containerized Node.js environment using Podman. See `tools/code/execute_playwright.py` for details.

## Requirements
- Python 3.11.12 (see `.python-version`)
- [uv](https://github.com/astral-sh/uv) (for dependency and venv management)
- [Ollama](https://ollama.com/) running locally (default: `http://localhost:11434`)
- [Podman](https://podman.io/) installed and running as a user service

## Setup

1. **Clone the repo:**
   ```sh
   git clone computron_9000
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

4. **Enable Podman systemd socket (required):**
   ```sh
   systemctl --user enable --now podman.socket
   ```

5. **Install dependencies:**
   ```sh
   uv pip install -r pyproject.toml
   ```

6. **Start the application:**
   ```sh
   uv run main.py
   ```
6. **Pull playwright image:**
   ```sh
   docker pull mcr.microsoft.com/playwright:v1.50.0-noble
   ```

7. **Open the chat UI:**
   - Visit [http://localhost:8080](http://localhost:8080) in your browser.

## Usage
- Type your message and press Enter or click Send.

## Agents

### Web Agent

The `web` agent is an expert AI agent specialized in navigating, searching, and extracting information from the web. It can:
- Fetch and extract content from web pages
- Automate web navigation and multi-step workflows using Playwright

The web agent is used by COMPUTRON_9000 as a tool for all web-based tasks, enabling advanced workflows such as multi-page navigation and summarization.

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License
[MIT](LICENSE)

## Maintainer Notes
For maintainers, summarization logic that calls the Ollama AsyncClient has been refactored into a new utility function `generate_summary_with_ollama` in `utils/summarizer/ollama.py`. All direct calls to `AsyncClient().generate` in this module now use the new utility. Tests for the utility are in `tests/utils/summarizer/test_ollama.py`.

