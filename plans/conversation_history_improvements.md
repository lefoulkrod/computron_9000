# Conversation History Improvements

## Bugs

1. **Summary role is `user`, breaks turn alternation**
   - After compaction: `user(pinned) -> user(summary) -> user(latest)` — three consecutive user messages
   - Also causes summary to render as user bubble on resume
   - **Fix**: Change to `role: "assistant"` in `_strategy.py:213-216`

2. **System message persisted in saved history**
   - `message_handler.py:274` saves `session.history.messages` including system message
   - Stale on resume — `_refresh_system_message()` rebuilds it anyway
   - **Fix**: Save `session.history.non_system_messages` instead

3. **`SummaryRecord` missing metadata for evaluation**
   - No `conversation_id` — can't link a summary record back to its conversation
   - No `agent_name` — sub-agent compactions are orphaned, indistinguishable from main agent
   - No `options` — no record of `num_ctx`, `num_predict`, `temperature`, etc. so can't tell which summarizer config produced which record
   - **Fix**: Add three fields to `SummaryRecord` model (`conversations/_models.py`), all with empty defaults for backward compat with existing persisted JSON. In `apply()`, read `conversation_id` and `agent_name` from existing ContextVars rather than threading through constructors:
     - `_conversation_id` ContextVar in `sdk/loop/_turn.py:51` (renamed in Step 0) — set in `turn_scope()`, inherited by sub-agents automatically. Expose a public `get_conversation_id()` getter.
     - `_context_stack` ContextVar in `sdk/events/_context.py:41` — stack of `(context_id, agent_name)` frames, pushed by `agent_span()`. Top of stack has the current agent name. Expose a public getter.
     - `_resolve_model(load_config())` in `apply()` captures the resolved options dict.
     - No constructor changes or call-site changes needed — the strategy reads context at apply time.

## Implementation

### Step 0 (prereq): Rename `session_id` → `conversation_id` throughout the app

The codebase inconsistently uses `session_id` and `conversation_id` for the same concept. The persistence layer (`conversations/`) already uses `conversation_id`. Align everything else.

**4 files, ~26 occurrences:**

#### Python backend
- `server/aiohttp_app.py` — `ChatRequest.session_id` field, query params in `stop_handler`/`delete_history_handler`, all local usages
- `server/message_handler.py` — `_DEFAULT_SESSION_ID` → `_DEFAULT_CONVERSATION_ID`, `_sessions` → `_conversations`, `_get_session()` → `_get_conversation()`, `reset_message_history(session_id=)` → `reset_message_history(conversation_id=)`, `handle_user_message(session_id=)` → `handle_user_message(conversation_id=)`, eliminate `conv_id = session_id or "default"` intermediary
- `sdk/loop/_turn.py` — `_DEFAULT_SESSION_ID` → `_DEFAULT_CONVERSATION_ID`, `_active_sessions` → `_active_conversations`, `_session_id` ContextVar → `_conversation_id` (string name too), `request_stop(session_id=)` → `request_stop(conversation_id=)`, `is_turn_active(session_id=)` → `is_turn_active(conversation_id=)`, `queue_nudge(session_id,)` → `queue_nudge(conversation_id,)`, `turn_scope(session_id=)` → `turn_scope(conversation_id=)`

#### Frontend
- `server/ui/src/hooks/useStreamingChat.js` — `sessionIdRef` → `conversationIdRef`, `sessionId` param → `conversationId`, `body.session_id` → `body.conversation_id`, URL query params `session_id=` → `conversation_id=`

#### API contract change
- Request body field: `session_id` → `conversation_id`
- Query params: `?session_id=` → `?conversation_id=`
- No external consumers, so no backward compat needed

### Step 1: Summary role `user` -> `assistant` (+ serialization fix)

#### 1a. Change role in inserted summary
- `sdk/context/_strategy.py:213-216` — change `"role": "user"` → `"role": "assistant"` in `history.insert()`

#### 1b. Fix `_serialize_messages()` — summary skip must be role-agnostic
- `sdk/context/_strategy.py:389-422`
- The `_SUMMARY_PREFIX` skip logic (lines 417-419) only fires for `role == "user"`. After changing summary role to `assistant`, this skip won't fire — the summary text will be serialized into the next compaction's input alongside the prior summary from `_extract_prior_summary()`, causing double-inclusion.
- **Fix**: Move the `_SUMMARY_PREFIX` check to the top of the loop, before role branching. This also handles migration — old conversations with `role: "user"` summaries are still skipped.

#### 1c. No changes needed
- `_find_first_user()` (line 329): Only checks `role == "user"`, so assistant-role summaries are naturally skipped. The `_SUMMARY_PREFIX` guard is legacy safety for old conversations.
- `_extract_prior_summary()` (line 340): Already role-agnostic (checks content prefix only).
- UI `_historyToMessages()`: Summaries render as assistant bubbles instead of user bubbles — correct behavior.

### Step 2: Exclude system message from saved history
- `server/message_handler.py:274` — `save_conversation_history(conv_id, session.history.non_system_messages)`
- Safe because `_refresh_system_message()` is called every turn (line 233) and rebuilds with fresh memory. Old saved histories with system message at index 0 also work — `set_system_message()` detects and replaces it.

### Step 3: Add metadata to SummaryRecord

#### 3a. Add fields to model
- `conversations/_models.py` — add `conversation_id: str = ""`, `agent_name: str = ""`, `options: dict[str, Any] = Field(default_factory=dict)`
- Defaults ensure backward compat with existing persisted records

#### 3b. Expose public getters for ContextVars
- `sdk/loop/_turn.py` — add `get_conversation_id() -> str | None` that returns `_conversation_id.get()` (renamed in Step 0); export from `sdk/loop/__init__.py`
- `sdk/events/_context.py` — add `get_current_agent_name() -> str | None` that reads top of `_context_stack`; export from `sdk/events/__init__.py`

#### 3c. Read context + capture options in `apply()`
- `sdk/context/_strategy.py` in `apply()` — after successful summarization:
  - Call `get_conversation_id()` for `conversation_id` (falls back to `""` if None)
  - Call `get_current_agent_name()` for `agent_name` (falls back to `""` if None)
  - Call `_resolve_model(load_config())` to capture resolved options dict
  - Pass all three to `SummaryRecord()`
- No constructor changes, no call-site changes — `SummarizeStrategy()` instantiation stays as-is everywhere

### Step 4: Tests
- `tests/sdk/context/test_strategy.py` (deleted — needs recreation)
- Summary inserted as assistant role
- Turn alternation correct after compaction
- `_serialize_messages` skips summary regardless of role (new `assistant` + legacy `user`)
- `_extract_prior_summary` finds assistant-role summary
- `_find_first_user` skips assistant summary
- `SummaryRecord` includes `conversation_id`, `agent_name`, `options`
- Legacy `role: "user"` summary migration works

### Step 5: Agent attribution on resumed messages

Currently during streaming, `agent_name` and `depth` come from SSE events. Saved history is raw LLM dicts without these fields, so resumed conversations lose agent labels.

#### 5a. Stamp `agent_name` on assistant messages when appended to history
- `sdk/loop/_tool_loop.py:241` — add `"agent_name"` to `assistant_message` dict, read from `get_current_agent_name()` (exposed in Step 3b)
- This metadata is inert to the LLM (it ignores unknown fields) but persists through save/load

#### 5b. Read `agent_name` in `_historyToMessages()`
- `server/ui/src/hooks/useStreamingChat.js:103-112` — when building assistant UI messages, pass through `agent_name: msg.agent_name || null`
- The `AssistantMessage` component already renders `agent_name` in the header — no component changes needed

## Not fixing (low impact)
- ContextManager not restored on resume — fill_ratio self-corrects after first LLM response
