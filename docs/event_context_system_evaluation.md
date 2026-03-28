# Deep Evaluation: Event/Context System

## Context

A deep evaluation of the event and context system used by Computron 9000. Read-only analysis — no code changes proposed.

---

## System Overview

The event/context system is a **two-layer architecture**:

1. **Events layer** (`sdk/events/`) — A pub/sub system for streaming real-time UI updates (screenshots, terminal output, context usage, etc.) from tool/agent code to the frontend via JSONL-over-HTTP.

2. **Context layer** (`sdk/context/`) — Manages conversation history, token tracking, and context window compaction (summarization) to keep conversations within model limits.

These two layers are bridged by the **tool loop** (`sdk/loop/`) and **hooks** (`sdk/hooks/`), which orchestrate the LLM call cycle and wire events/context together.

---

## Architecture Diagram

```
HTTP Request
    │
    ▼
message_handler.handle_user_message()
    │
    ├─ Creates/gets Session (ConversationHistory + ContextManager)
    ├─ asyncio.Queue bridges events to HTTP stream
    │
    ▼
turn_scope()                          ← Creates EventDispatcher, stop event, nudge queue
    │                                    Binds dispatcher to ContextVar
    ▼
agent_span()                          ← Pushes agent_name/depth onto context stack
    │
    ▼
run_tool_call_loop()                  ← Main LLM + tool execution loop
    │
    ├─ before_model hooks             ← ContextHook.before_model → apply_strategies()
    ├─ provider.chat()                ← LLM call
    ├─ after_model hooks              ← ContextHook.after_model → record_response()
    ├─ publish_event(content/thinking)
    ├─ for each tool_call:
    │     ├─ publish_event(ToolCallPayload)
    │     ├─ execute tool (may publish own events: screenshots, terminal, etc.)
    │     └─ append tool result to history
    └─ publish_event(final=True)
         │
         ▼
    EventDispatcher.publish()         ← Fans out to all subscribers
         │
         ▼
    _queue_handler → asyncio.Queue    ← Bridge to HTTP streaming
         │
         ▼
    stream_events() → JSONL response  ← Client receives events line by line
         │
         ▼
    useStreamingChat.js               ← Frontend parses JSONL, updates React state
```

---

## Evaluation

### Strengths

**1. Clean separation of concerns**
- Events, context, and the tool loop are genuinely decoupled. The event layer knows nothing about context management, and vice versa. They only touch through the thin `ContextHook` and the `ContextUsagePayload` event.

**2. ContextVar-based implicit threading**
- Using `ContextVar` for the dispatcher, stop event, session ID, model options, and context stack means none of these need to be threaded through every function signature. Tools like `publish_event()` just work from anywhere in the call tree.
- Sub-agents naturally inherit the dispatcher but can push their own `agent_span`, getting automatic depth/attribution tagging.

**3. Well-designed event model**
- Discriminated union payloads (`Field(discriminator="type")`) make the schema extensible — new event types can be added without breaking existing consumers.
- `AgentEvent` as a uniform envelope with optional fields supports both streaming partials and complete events.
- Pydantic validation ensures type safety at serialization boundaries.

**4. Robust turn lifecycle**
- `turn_scope()` is a clean async context manager that sets up and tears down all per-turn state (dispatcher, stop event, nudge queue, session tracking).
- `drain()` before teardown ensures no events are lost.
- Per-session isolation (separate stop events, nudge queues) prevents cross-session interference.

**5. Pluggable strategy pattern for context management**
- `ContextStrategy` protocol allows adding new strategies without modifying `ContextManager`.
- `SummarizeStrategy` is well-implemented: pinned first user message, chunked summarization for long conversations, page snapshot deduplication, tool result truncation, prior summary merging.
- `SummaryRecord` persistence enables quality evaluation of compaction decisions.

**6. Nudge queue for concurrent messages**
- Elegant solution for handling user messages that arrive while a turn is active — queued and drained via `NudgeHook` before the next model call.

**7. ConversationHistory encapsulation**
- Read-only `.messages` property returns a copy, preventing accidental mutation.
- Controlled mutation via explicit methods (`append`, `drop_range`, `insert`, `set_system_message`).

### Potential Issues & Weaknesses

**1. Sync handler scheduling via `call_soon` is fragile**
- `EventDispatcher.publish()` schedules sync handlers with `loop.call_soon()`. This means they run on the next event loop iteration, *not* immediately. If a sync handler modifies shared state that an async handler also reads, there's a potential ordering issue.
- More importantly: sync handler exceptions scheduled via `call_soon` are **silently swallowed** by the event loop unless a custom exception handler is installed. The `_run_sync_handler` wrapper catches exceptions, but if `call_soon` itself fails or the callback isn't reached, errors vanish.
- **Suggestion**: Consider making all handlers async, or at minimum wrapping sync handlers in `create_task` too for consistent error handling.

**2. `ConversationHistory.messages` copies on every access**
- `.messages` returns `list(self._messages)` — a full shallow copy every time. This is called on every LLM call (`history.messages` in `_chat_with_retries`), and `.non_system_messages` also copies. For long conversations this creates unnecessary GC pressure.
- **Suggestion**: Consider returning a read-only view (e.g., `tuple` or a `Sequence` wrapper) instead of a mutable copy, or caching the snapshot.

**3. Double strategy execution on first iteration**
- In `message_handler.py`, `ctx_manager.apply_strategies()` is called explicitly before `run_tool_call_loop()`. Then inside the loop, `ContextHook.before_model` calls `apply_strategies()` again on iteration 1. This means strategies are evaluated twice on the first model call.
- The `SummarizeStrategy` is idempotent (won't re-summarize if fill ratio dropped), so this is harmless but wasteful — it still evaluates `should_apply()` and calls `_tracker.stats` twice.
- **Suggestion**: Remove the explicit `apply_strategies()` call in `message_handler.py` since the hook handles it.

**4. Token tracking relies on last-call-only stats**
- `ContextStats.context_used` stores only the token count from the *last* LLM call, not cumulative usage. `fill_ratio` is computed as `context_used / context_limit`. This means after a compaction (which doesn't involve a new LLM call), the stats still reflect the pre-compaction fill ratio until the next model call.
- This is fine for the summarization trigger (it fires before the model call, using stale-but-conservative stats), but the `ContextUsagePayload` sent to the UI after compaction may show a fill ratio that doesn't reflect the reduced history.

**5. No backpressure on event publishing**
- `publish()` fires and forgets — if the `_queue_handler` in `message_handler.py` can't keep up (e.g., slow network write), the `asyncio.Queue` grows unbounded. For high-frequency events like `TerminalOutputPayload` streaming or `GenerationPreviewPayload` steps, this could cause memory pressure.
- **Suggestion**: Consider a bounded queue with a drop-oldest policy for non-critical events.

**6. `_subcontext_counter` is module-level and never resets**
- `itertools.count(1)` in `_context.py` monotonically increases across all sessions and server restarts (within the process). Context IDs like `root.browser_agent.47382` are functional but opaque. Not a bug, but worth noting for debuggability.

**7. Hook protocol is implicit (duck typing)**
- Hooks are checked with `getattr(hook, "before_model", None)` — there's no formal protocol or base class. This is flexible but means typos in method names silently result in hooks being skipped.
- **Suggestion**: Define a `Hook` protocol class similar to `ContextStrategy`.

**8. `ContextManager` doesn't own its `ConversationHistory`**
- The docstring explicitly states this, but it means the history can be mutated externally (e.g., `message_handler.py` appends user messages directly). This is intentional but creates an implicit contract: the manager assumes the history it tracks is the same one being modified.

**9. Summarizer model resolution happens per-call**
- `_call_summarizer` calls `load_config()` and `get_provider()` on every invocation. If config is loaded from disk, this is wasteful for chunked summarization (which may call the summarizer 3-4 times in sequence).

**10. Event enrichment creates a model copy every time**
- `publish_event()` calls `event.model_copy(update={...})` to stamp `agent_name` and `depth`. This creates a new Pydantic model instance for every event. For high-frequency events (screenshots at 10fps), this adds overhead.
- **Suggestion**: Mutate the event in-place before dispatch (it's not shared), or pass attribution as dispatcher metadata.

### Design Quality Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Separation of concerns | Excellent | Events, context, loop, hooks are cleanly separated |
| Extensibility | Excellent | Discriminated unions, strategy protocol, hook system |
| Testability | Very good | ContextVar no-ops in tests, controllable dispatcher |
| Error handling | Good | Defensive try/except everywhere, but sync handler edge cases |
| Performance | Adequate | Copy-on-access history, per-event model_copy, unbounded queue |
| Type safety | Good | Pydantic models, but hooks lack formal protocol |
| Debuggability | Good | Rich console logging, SummaryRecord audit trail |
| Concurrency safety | Good | Per-session isolation, but no backpressure |

### Overall

This is a well-architected system. The core abstractions (EventDispatcher, ContextVar-based publishing, ConversationHistory, ContextStrategy protocol, turn_scope lifecycle) are clean and composable. The main areas for improvement are performance optimizations (history copying, event enrichment overhead) and hardening (backpressure, formal hook protocol, eliminating double strategy evaluation). None of the issues are critical — the system works correctly and is maintainable.
