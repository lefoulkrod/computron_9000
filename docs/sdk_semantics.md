# SDK Semantics

Core concepts and their relationships in the Computron 9000 agent SDK.

## Conversation

A persistent, multi-turn exchange between user and agent(s), identified
by a string `conversation_id` (default: `"default"`).

A conversation owns:
- **ConversationHistory** — ordered list of messages (system, user, agent, tool)
- **ContextManager** — tracks token usage and runs compaction strategies

Conversations are stored in a global dict in `server/message_handler.py` and
can be persisted to disk and resumed. Multiple conversations can be active
concurrently, each isolated by their ID.

**Defined in:** `sdk/context/_history.py`, `sdk/context/_manager.py`,
`server/message_handler.py`

## Turn

A single user message → agent response cycle. One turn includes:
- The user message that triggered it
- All LLM calls, tool executions, and sub-agent work needed to produce a response
- All events emitted during that work

`turn_scope(conversation_id)` is the async context manager that sets up and
tears down a turn's resources:
- A fresh `EventDispatcher` bound via ContextVar
- A per-conversation stop event for cooperative cancellation
- A nudge queue for injecting messages into the root agent's loop
- Conversation liveness tracking

A conversation contains many turns, executed sequentially.

### Hooks

Hooks are pluggable callbacks invoked at defined phases of a turn. They let
the server layer behavior (persistence, context management, logging) onto the
core loop without modifying it. The phases, in order:

- `on_turn_start(agent_name)` — before any LLM work begins
- `before_model(history, iteration, agent_name)` — before each LLM call
- `after_model(response, history, iteration, agent_name)` — after each LLM call (can rewrite the response)
- `before_tool(tool_name, arguments)` — before each tool execution (can intercept)
- `after_tool(tool_name, arguments, result)` — after each tool execution (can rewrite result)
- `on_turn_end(final_content, agent_name)` — after the turn completes (always runs, even on error)

**Defined in:** `sdk/turn/_turn.py`, `sdk/turn/_execution.py`

## Agent Span

A hierarchical execution context wrapping one agent's work within a turn.
The root agent gets depth 0; each sub-agent it spawns gets depth 1+.

`agent_span(context_id, agent_name)` is a context manager that:
- Pushes onto a ContextVar stack so `publish_event()` can attribute events
- Emits `AgentStartedPayload` on entry, `AgentCompletedPayload` on exit
- Generates hierarchical IDs (e.g. `root`, `root.browser_agent.1`)

Agent spans nest naturally — sub-agents inherit the parent's turn context
(dispatcher, conversation ID, stop event) via ContextVar semantics, but get
their own position in the context stack.

**Defined in:** `sdk/events/_context.py`

## Message Group

A logical unit used during context compaction: **one agent message plus
its associated tool-call results**. This ensures tool calls and their results
are never split at compaction boundaries, preventing orphaned tool results
that confuse the LLM.

Compaction strategies use `keep_recent_groups` to count backward from the
tail of the conversation history, preserving the N most recent groups
verbatim while summarizing or clearing older ones.

**Defined in:** `sdk/context/_strategy.py` (`_count_kept_by_assistant_groups`)

## Event

A discrete, typed message emitted during a turn describing what the agent is
doing, thinking, or producing. Events flow from agents/tools → EventDispatcher
→ subscribers (typically the SSE handler streaming to the frontend).

Events are published via `publish_event()`, which enriches them with the
current agent span's `agent_name`, `agent_id`, and `depth` before dispatching.
This keeps call sites simple — tools just publish the event, attribution is
automatic.

**Defined in:** `sdk/events/_models.py`, `sdk/events/_dispatcher.py`,
`sdk/events/_context.py`

## Relationships

```
Conversation
│   owns ConversationHistory + ContextManager
│   identified by conversation_id
│
├── Turn 1 (user message → agent response)
│   │   scoped by turn_scope(conversation_id)
│   │   owns EventDispatcher, stop event, nudge queue
│   │
│   ├── Agent Span: root (depth=0)
│   │   ├── LLM call → tool calls → LLM call → ...
│   │   ├── Agent Span: sub-agent (depth=1)
│   │   │   └── LLM call → tool calls → ...
│   │   └── Agent Span: another sub-agent (depth=1)
│   │       └── ...
│   │
│   └── Events flow: publish_event() → dispatcher → subscribers → UI
│
├── Turn 2
│   └── ...
│
└── Compaction (between turns)
    └── Operates on message groups within ConversationHistory
```
