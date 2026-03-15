# Agent Capability Ideas

## High Leverage

### HTTP Client Tool
Right now web access is only through the browser agent, which is heavy. A lightweight `http_request(method, url, headers, body)` tool would let agents hit APIs, download files, check endpoints without spinning up Playwright.

### Structured Data / DuckDB Tool
The agent can do this via bash+python, but a first-class `query_data(sql, files)` tool that auto-loads CSVs/JSON/Parquet into DuckDB would make data analysis tasks dramatically faster and more reliable.

### Human-in-the-Loop Gates
An `ask_user(question)` tool that pauses execution, pushes a question to the UI, and resumes when the user responds. Right now the agent has to either guess or fail on ambiguous tasks.

## Medium Leverage

### Git Tools
`git_diff`, `git_commit`, `git_log` for the workspace. Agents could checkpoint their own work, revert bad changes, and reason about file history without fragile bash parsing.

### Notification / Callback
`notify_user(message)` that sends a push/email/webhook when a long-running task finishes. Useful once tasks take 5+ minutes.

### Vector Memory / RAG
Current memory is key-value. A `search_memory(query) -> [relevant chunks]` backed by embeddings would let the agent recall relevant context from past conversations without exact key lookups.

### MCP Server Support
Let users plug in arbitrary Model Context Protocol servers. Instantly gives the agent access to Slack, GitHub, databases, Notion, etc. without hardcoding each integration.

## Fun / Experimental

### Computer Use (Screenshot + Click)
If already running Podman containers, run a desktop environment and give the agent `screenshot()` + `mouse_click(x, y)` + `keyboard_type(text)` for GUI apps (LibreOffice, GIMP, etc.).

### Agent-to-Agent Messaging
Right now sub-agents are fire-and-forget. A shared message queue or scratchpad that agents can read/write concurrently would enable collaborative workflows (one agent researches while another builds).

### Self-Evaluation Hook
After each task, the agent scores its own output and writes a brief reflection. Feed those into the skills system so it improves over time. Partway there with skill extraction already.

### Scheduled Tasks
`schedule_task(cron_expr, instructions)` so the agent can set up recurring work: "check this URL every hour", "regenerate this report daily."
