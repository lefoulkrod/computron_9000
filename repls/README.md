# REPLs

This folder contains developer convenience REPL scripts that let you exercise
individual tools and agents interactively. They are not part of the production
API, but are useful for debugging and manual experimentation.

Available REPLs

- `browser_tools_repl.py` — Interactive menu exposing individual browser tools
  (open_url, click, fill_field, extract_text, ask_about_screenshot, ...).
  Run with:

  ```sh
  uv run python -m repls.browser_tools_repl
  ```

- `browser_agent.py` — REPL that forwards input to the BROWSER_AGENT. The agent
  decides when to call browser tools and maintains message history across turns.
  Run with:

  ```sh
  uv run python -m repls.browser_agent
  ```

- `generate_completion_repl.py` — Simple REPL for `generate_completion` (LLM text
  generation). Supports toggling `think` mode and switching models.

  ```sh
  uv run python -m repls.generate_completion_repl
  ```

- `generate_bash_cmd_repl.py` — REPL to execute bash commands inside the virtual
  computer container via the `run_bash_cmd` tool.

  ```sh
  uv run python -m repls.generate_bash_cmd_repl
  ```

- `reddit_repl.py` — Search Reddit and view comments interactively (requires
  Reddit credentials configured in `.env`).

  ```sh
  uv run python -m repls.reddit_repl
  ```

- `tool_test_repl.py` — Runs predefined end-to-end tool test scenarios (text
  patching workflows). Intended for automated/manual tool testing.

  ```sh
  uv run python -m repls.tool_test_repl -w <workspace>
  ```

- `test_coder_workflow_repl.py` — REPL to exercise coder agents (architect,
  planner, coder, verifier) and run the coder workflow. Switch agents with
  `/agent <name>` inside the REPL.

  ```sh
  uv run python -m repls.test_coder_workflow_repl
  ```

Notes

- Many REPLs assume the project root is on `PYTHONPATH`. Using `uv run` from
  the project root ensures correct imports.
- Some REPLs require external credentials (e.g., Reddit) or a running Ollama
  instance for model-backed functionality.

Example

Start the browser tools REPL from the project root and try a quick command:

```sh
PYTHONPATH=. uv run python -m repls.browser_tools_repl
```
