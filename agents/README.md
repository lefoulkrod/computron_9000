# Agents

Agent definitions and the SDK that powers the tool-call loop.

## Agent Architecture

### The Three Agents

| Agent | Role | Has Browser | Has Custom Tools | Default Location |
|-------|------|:-----------:|:----------------:|------------------|
| **Computron** | Top-level orchestrator — decomposes tasks, delegates to sub-agents | via browser agent tool | yes | `ollama/computron/` |
| **Browser Agent** | Browses the web using Playwright tools | yes | no | `ollama/browser/` |
| **Sub-Agent** | Worker for code, file processing, data analysis | no | yes | `ollama/sub_agent/` |

Computron delegates browsing to the browser agent and heavy computation to sub-agents. Sub-agents **cannot** browse — they have no browser tools.

### Agent-as-Tool Pattern

`make_run_agent_as_tool_function()` in `ollama/sdk/run_agent_tools.py` wraps an agent as a callable tool function. The browser agent is created this way — Computron sees it as a tool called `run_browser_agent_as_tool(instructions)`.

The factory captures static config (name, system prompt, tools) at import time but reads dynamic options (model, think, max_iterations) from context vars at call time.

## Iteration Limits (`max_iterations`)

Controls how many tool-call loop iterations an agent can perform before being forced to stop.

### How It Works

The tool loop in `ollama/sdk/tool_loop.py` tracks iterations. When the limit is hit:

1. A "wrap up" message is injected: `"Tool call budget exhausted. Wrap up and respond."`
2. The tools list is set to `[]` — the model can only produce text
3. The normal loop path handles the final response (no code duplication)

A value of **0 means unlimited** — the loop runs until the model stops calling tools naturally.

### How Limits Flow

```
UI (Settings panel)
  → useModelSettings.js (unlimitedTurns toggle + agentTurns number)
  → useStreamingChat.js (_buildRequestBody → opts.max_iterations)
  → POST /api/chat { options: { max_iterations: N } }
  → server/aiohttp_app.py (ChatRequest → LLMOptions)
  → agents/ollama/message_handler.py (options.max_iterations → Agent)
  → agents/ollama/sdk/tool_loop.py (budget check in while loop)
```

For nested agents (browser, sub-agent), limits propagate via context vars:

```
message_handler.py
  → set_model_options(options)        # stores LLMOptions in ContextVar
  → run_agent_tools.py               # get_model_options().max_iterations
  → sub_agent/agent.py               # get_model_options().max_iterations
```

### Configuration

**From the UI** (per-request): The Settings panel has a "Turns" row with:
- A toggle for unlimited (default: ON)
- When toggled OFF, a number input appears (default: 15)

When unlimited is ON, no `max_iterations` is sent → backend gets `None` → agents use default of 0 (unlimited).

### Key Types

- `LLMOptions.max_iterations` (`agents/types.py`) — optional int from UI, `None` = not set
- `Agent.max_iterations` (`agents/types.py`) — int on the agent model, `0` = unlimited

## Model Options Propagation

Per-request model options (model name, think, temperature, max_iterations, etc.) are set once in `message_handler.py` via `set_model_options()` and read by any nested agent via `get_model_options()`. Both live in `ollama/sdk/events/context.py` using `contextvars.ContextVar`.

## SDK Structure

| File | Purpose |
|------|---------|
| `ollama/sdk/tool_loop.py` | Core `run_tool_call_loop()` — chat loop with tool execution and budget enforcement |
| `ollama/sdk/run_agent_tools.py` | `make_run_agent_as_tool_function()` factory + result type conversion |
| `ollama/sdk/events/context.py` | Event publishing, agent spans, stop mechanism, model options context vars |
| `ollama/sdk/events/models.py` | `AgentEvent` event model |
| `ollama/sdk/events/dispatcher.py` | Async event dispatcher with subscriptions |
| `ollama/sdk/hooks.py` | Unified hook system: `HookContext`, `HookResult`, built-in hooks, `run_hooks()` |
| `ollama/message_handler.py` | Entry point — wires up Computron agent, manages message history, streams events |
