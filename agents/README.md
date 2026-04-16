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

### Sub-Agents

Sub-agents are spawned via `spawn_agent(instructions, profile, agent_name=...)`. Each sub-agent runs in its own context with the model, skills, system prompt, and inference parameters from its explicit `AgentProfile`. Sub-agents do not inherit settings from their parent.

## Iteration Limits (`max_iterations`)

Controls how many tool-call loop iterations an agent can perform before being forced to stop.

### How It Works

The tool loop in `ollama/sdk/tool_loop.py` tracks iterations. When the limit is hit:

1. A "wrap up" message is injected: `"Tool call budget exhausted. Wrap up and respond."`
2. The tools list is set to `[]` — the model can only produce text
3. The normal loop path handles the final response (no code duplication)

A value of **0 means unlimited** — the loop runs until the model stops calling tools naturally.

### How Limits Flow

`max_iterations` is set on the `AgentProfile` and flows to the `Agent` via `build_agent(profile, tools=...)` from the `agents` package. Sub-agents spawned through `spawn_agent()` get their own profile and their own `max_iterations` — no inheritance from the parent.

### Key Types

- `AgentProfile.max_iterations` — optional int, `None` = not set
- `Agent.max_iterations` (`agents/types.py`) — int on the agent model, `0` = unlimited
