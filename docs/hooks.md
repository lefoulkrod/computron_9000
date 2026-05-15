# Hooks

Hooks are pluggable callbacks invoked at six phases of a turn:
`on_turn_start`, `before_model`, `after_model`, `before_tool`, `after_tool`, `on_turn_end`.

Each hook class implements one or more of these methods. The turn engine
(`sdk/turn/_execution.py`) calls them in registration order.

## Default hook chain

`default_hooks()` in `sdk/hooks/_default.py` returns the standard set used
by all agents, in this order:

| Order | Hook | Condition |
|-------|------|-----------|
| 1 | NudgeHook | always |
| 2 | StopHook | always |
| 3 | BudgetGuard | `max_iterations > 0` |
| 4 | LoopDetector | always |
| 5 | LoggingHook | always |
| 6 | ScratchpadHook | always |
| 7 | LoadedSkillHook | always |
| 8 | ToolResultCapHook | `num_ctx > 0` |
| 9 | ContextHook | `ctx_manager` provided |

## Hook catalog

### NudgeHook
- **File:** `sdk/hooks/_nudge_hook.py` (28 lines)
- **Methods:** `before_model`
- **Purpose:** Drains queued nudge messages and injects them into the conversation history. Each agent has its own nudge queue keyed by agent ID, so nudges can target any agent (root or sub-agent).

### StopHook
- **File:** `sdk/hooks/_stop_hook.py` (32 lines)
- **Methods:** `before_model`, `after_model`
- **Purpose:** Checks for a user-requested stop signal. At `before_model`, raises `StopRequestedError` before the LLM call. At `after_model`, strips tool calls from the response and injects a wrap-up message so the agent finishes cleanly.

### BudgetGuard
- **File:** `sdk/hooks/_budget_guard.py` (36 lines)
- **Methods:** `before_model`
- **Purpose:** Appends a budget-exhaustion nudge to the history when the turn exceeds `max_iterations`, telling the agent to wrap up.

### LoopDetector
- **File:** `sdk/hooks/_loop_detector.py` (63 lines)
- **Methods:** `after_tool`, `before_model`
- **Purpose:** Tracks tool-call signatures across iterations. When the same signature repeats N rounds in a row, injects a nudge telling the agent to try a different approach.

### LoggingHook
- **File:** `sdk/hooks/_logging_hook.py` (136 lines)
- **Methods:** `before_model`, `after_model`
- **Purpose:** Logs model inputs and outputs using Rich panels and tables — message counts, response content, tool calls, token usage, and timing.

### ScratchpadHook
- **File:** `sdk/hooks/_scratchpad_hook.py` (97 lines)
- **Methods:** `after_tool`
- **Purpose:** Displays Rich panels when the agent uses scratchpad tools (`save_to_scratchpad`, `recall_from_scratchpad`) for visibility into agent state management.

### LoadedSkillHook
- **File:** `sdk/hooks/_loaded_skill_hook.py` (51 lines)
- **Methods:** `before_model`
- **Purpose:** Rebuilds the skill section of the system message before each model call so newly loaded skills appear immediately.

### ToolResultCapHook
- **File:** `sdk/hooks/_result_cap.py` (43 lines)
- **Methods:** `after_tool`
- **Purpose:** Replaces tool results that exceed the model's context window (`num_ctx * 4` characters) with an error message telling the agent to retry with a narrower request.

### ContextHook
- **File:** `sdk/hooks/_context_hook.py` (29 lines)
- **Methods:** `before_model`, `after_model`
- **Purpose:** Runs context management strategies (compaction, chunking) before the model call and records token usage from responses afterward.

## Non-default hooks

These are instantiated separately by the server, not through `default_hooks()`.

### PersistenceHook
- **File:** `sdk/hooks/_persistence.py` (52 lines)
- **Methods:** `on_turn_end`
- **Purpose:** Saves conversation history to disk when the turn ends. Handles both main agent and sub-agent history.

### AgentEventBufferHook
- **File:** `sdk/hooks/_agent_event_buffer.py` (111 lines)
- **Methods:** Event handler (not standard hook phases)
- **Purpose:** Buffers agent lifecycle events for persistence — keeps the last screenshot per agent, caps terminal output at 50 events per agent, and collects file output and lifecycle events.

## Test coverage

| Hook | Tested |
|------|--------|
| NudgeHook | no |
| StopHook | no |
| BudgetGuard | yes |
| LoopDetector | yes |
| LoggingHook | no |
| ScratchpadHook | yes |
| LoadedSkillHook | no |
| ToolResultCapHook | yes |
| ContextHook | yes |
| PersistenceHook | no |
| AgentEventBufferHook | no |
