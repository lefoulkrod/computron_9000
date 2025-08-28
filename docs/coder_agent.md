"""Coder agent documentation."""

# Coder Agent

The `coder_agent` is an agent designed for code generation, analysis, and execution using the `qwen2.5-coder` model.

## Features
- Generates and analyzes code
- Executes code using available tools
- Uses the qwen2.5-coder model for advanced code tasks

## Usage
Import and use the agent in your application:

```python
from agents.ollama.coder import coder_agent, coder_agent_tool
```

## Tools
- `execute_code`: Executes code snippets in a secure environment

## Tests
Tests are located in `tests/agents/ollama/coder/`.
