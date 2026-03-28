# Multi-Agent Architecture Overhaul

## Context

The current architecture runs tool calls sequentially (`for tc in tool_calls` at `sdk/turn/_execution.py:313`). When the LLM responds with N tool calls, they run one at a time — only allowing a single linear chain of sub-agents. The browser is a process-level singleton, the desktop has one display, and the frontend treats preview state (browser screenshots, terminal output) as global singletons.

**Goal**: Enable a network of parallel sub-agents, each with scoped resources and previews, visualized in a new UI that shows agent lineage and per-agent preview panels.

**Incremental approach**: Phase 1 builds the new UI and per-agent scoping on top of the existing sequential execution. Phase 2 adds parallel execution, multi-browser, and resource locking.

### Mockups

All UI views at 1920x1080:

1. [Simple chat](mockup_01_simple_chat.png) — no agents spawned, standard chat experience
2. [Network overview](mockup_02_network_overview.png) — agent graph with chat panel on right
3. [Flyout panel](mockup_03_flyout_panel.png) — settings flyout over the network view
4. [Expanded browser agent](mockup_04_expanded_browser_agent.png) — activity stream + browser/terminal/files + nudge bar
5. [Expanded coder agent](mockup_05_expanded_coder_agent.png) — activity stream + terminal/files + nudge bar
6. [Expanded desktop agent](mockup_06_expanded_desktop_agent.png) — activity stream + VNC preview + nudge bar
7. [Desktop overlay](mockup_07_desktop_overlay.png) — user's personal desktop (display :99) floating over network
8. [Large network](mockup_08_large_network.png) — 14 agents across 4 levels, showing scalability

### UI Model

The left settings column is replaced by a narrow icon sidebar. Clicking an icon opens a **flyout panel** (~280px) that slides out over the content with a scrim overlay ([mockup_03_flyout_panel.png](mockup_03_flyout_panel.png)). Clicking outside or the same icon closes it. No full-expand option — flyout only. Panel components (ModelSettings, Memory, Conversations, Custom Tools) render flat content directly inside the flyout — no nested collapsible headers. The layout adapts based on context:

**Network overview** (monitoring all agents):
- **Left**: Collapsed icon sidebar (settings, memory, conversations)
- **Middle**: Agent network graph showing the full agent tree with cards ([mockup_02_network_overview.png](mockup_02_network_overview.png))
- **Right**: Chat panel — the user's conversation with the root agent. Used for initial instructions and nudging.

**Drilled into an agent** (observing one agent's work):
- **Left**: Collapsed icon sidebar
- **Middle**: Agent activity stream (thinking, content, tool calls) + scoped preview panels (browser, terminal, files) ([mockup_04_expanded_browser_agent.png](mockup_04_expanded_browser_agent.png))
- **Right**: Chat panel collapses. A compact floating nudge bar stays at the bottom of the view — nudges always queue for the root agent.
- "← Agents" button returns to the network overview. Breadcrumb shows lineage.

**No sub-agents** (simple chat, no network needed):
- **Left**: Collapsed icon sidebar
- **Middle**: Preview panels for the root agent (browser, terminal, files, desktop) — same as today's middle column. Shows when the root agent uses browser tools, runs bash commands, generates files, etc. Empty placeholder with network icon when no previews are active.
- **Right**: Chat panel with agent selector dropdown.

**Transition when sub-agents spawn**:
- The middle area transitions from root agent preview panels to the **agent network graph**. The root agent becomes a card in the graph like any other agent.
- To see the root agent's previews again, click its card in the network — same as any other agent.
- The root is not special in the graph view — it's just the top-level card. All agents (root and sub) are accessed the same way: click card → expanded view with activity stream + preview panels.
- When all sub-agents complete, the network stays visible (agents in "complete" state) so you can review any agent's work. Starting a new conversation resets to simple chat.

**Multi-turn conversations**: Each turn creates a new root agent with a unique ID. The network graph handles multiple roots (a forest) — all roots appear side-by-side at level 0, each with their own sub-agent trees below. Previous turns' agents show in "complete" state.

### Interaction Model

- The user only directly interacts with the **root agent** via chat. Sub-agents are "observe only" — their full activity (thinking, streaming output, tool calls, preview panels) is visible by clicking their card in the network.
- **Nudges always target the root agent.** In Phase 1, nudges queue and are processed when the root's next `before_model` runs (after current sub-agents finish). In Phase 2, the root agent may be able to relay nudges to running sub-agents.
- **Nudge routing fix**: Sub-agents must NOT drain the nudge queue. Only the root agent's `NudgeHook` should drain nudges. Uses public `get_current_depth()` API to check depth.
- When the root agent is running without sub-agents, the experience is identical to today's chat.

---

## Phase 1: New UI + Per-Agent Event Scoping (Sequential Execution)

### Task 1: Add `agent_id` to events — DONE ✓

Added `agent_id: str | None = None` to `AgentEvent`. `publish_event()` enriches it from the context stack. Added `get_current_agent_id()`, `get_current_depth()`, and `get_current_dispatcher()` public APIs.

### Task 2: Emit agent lifecycle events — DONE ✓

Added `AgentStartedPayload` and `AgentCompletedPayload`. `agent_span()` emits lifecycle events on entry/exit with catch-and-reraise for status detection. `run_turn()` re-raises `StopRequestedError`. `message_handler.py` catches it with `suppress(StopRequestedError)`. Added `instruction` parameter to `agent_span()`.

### Task 2b: Fix nudge routing — DONE ✓

`NudgeHook` uses `get_current_depth() > 0` to skip draining for sub-agents.

### Task 2c: Root agent lifecycle events — DONE ✓

Root agent was already wrapped in `agent_span()` in `message_handler.py`. Instruction passed through.

### Task 3: useAgentState hook — DONE ✓

React Context + useReducer at `server/ui/src/hooks/useAgentState.jsx`. Activity log merges consecutive content/thinking tokens to prevent per-token entry explosion. Shared `mergeTerminalEvent()` and `formatElapsed()` utilities in `server/ui/src/utils/agentUtils.js`.

### Task 4: Route events by agent_id — DONE ✓

`_handleStreamEvent()` passes `agent_id` with all callbacks. Sub-agent tokens (depth > 0) route to agent state reducer via `onAgentContent` callback. Root tokens continue to chat messages. New callbacks: `onAgentEvent`, `onAgentToolCall`, `onAgentContent`, `onAgentContextUsage`, `onAgentFileOutput`.

### Task 5: Wire AgentStateProvider — DONE ✓

`DesktopApp` wrapped in `AgentStateProvider`. All stream callbacks dispatch to both global state (backward compat for simple chat) and per-agent reducer state. `parentAgentId` coerced with `|| null` to handle `exclude_none=True` serialization.

### Task 6: AgentCard + AgentNetwork — DONE ✓

`AgentCard` with React.memo, status dots, badges, browser thumbnail, formatAgentName. `AgentNetwork` with SVG bezier connectors, BFS level layout, ResizeObserver, single-pass stats counting. Handles multi-root (forest) for multi-turn conversations.

### Task 7: Agent-aware layout — DONE ✓

Three contextual views: simple chat (no agents), network overview (sub-agents exist), expanded agent (selected). Sidebar with flyout panels.

### Task 8: AgentActivityView — DONE ✓

Two-pane layout: activity stream (left) + preview panels (right). Shared `MarkdownContent` component extracted from Message.jsx for markdown rendering. Thinking blocks match main chat style (left border, Hide/Show toggle with ChevronIcon). Tool calls rendered inline with wrench icon. Nudge bar at bottom. Breadcrumb navigation.

### Task 9: Remove sub-agent messages from chat — DONE ✓

Sub-agent streaming tokens routed to agent state reducer, not chat messages. Depth-based filtering removed from ChatMessages.

### Task 10: Redesign header + sidebar — DONE ✓

Slim 36px header with original computron logo, theme toggle, desktop button, new conversation. Icon sidebar with flyout panels. Panel components (ModelSettings, Memory, Conversations, CustomTools) stripped of collapsible wrappers — render flat content directly. Skills panel removed (skill extraction dropped). All CSS uses `var(--primary)`, `var(--secondary)`, `var(--button)`, `var(--text)` for theme support.

### Task 11: Agent state persistence — PARTIALLY DONE

**Backend done:**
- `AgentEventBufferHook` captures lifecycle, screenshot, terminal, file events during turn
- `save_agent_events()` / `load_agent_events()` in conversations store
- `delete_conversation()` cleans up `_agent_events.json`
- Buffer subscribed to dispatcher in `message_handler._run_turn()`
- Events saved after turn completion

**Not yet done:**
- Frontend replay on conversation resume (`REPLAY_EVENTS` reducer action)
- Resume API endpoint including agent events in response
- Removing `_sub_agents.json` and related code (skill extraction removal)
- Testing resume flow end-to-end

---

## Bugs Found and Fixed During Implementation

1. **`parent_agent_id: undefined` vs `null`** — Pydantic's `exclude_none=True` omits `None` fields from JSON. In JS, `undefined !== null` is `true`, causing `hasSubAgents()` to incorrectly return true for root-only conversations. Fixed with `|| null` coercion.

2. **Activity log token explosion** — Every streaming token dispatched a separate `APPEND_ACTIVITY` action. Fixed by merging consecutive same-type entries in the reducer.

3. **Root agent stuck on "running"** — `stream_events()` in `aiohttp_app.py` broke on `final=true` before the root's `agent_completed` event could be sent (it's published in `agent_span()`'s finally block, after `_publish_final()`). Fixed by removing the `break` — stream continues until the producer queue signals end.

4. **Multi-turn agents not showing** — `_buildLevels()` used a single `rootId` set from the first turn. Multi-turn conversations create multiple roots. Fixed by finding all root agents (parentId === null) and BFS from each.

5. **`_formatAgentName` ReferenceError** — Rename from `_formatAgentName` to `formatAgentName` missed a call site. Fixed.

6. **`useState` not defined crash** — Removed `useState` import from ModelSettingsPanel but `InfoTip` component still used it. Restored.

7. **Light mode not applying** — All new CSS files used hardcoded dark-mode colors. Fixed with CSS variables.

---

## Follow-up Items (Not Yet Done)

### UI Polish
- **CSS units inconsistency** — Original codebase uses `rem` for spacing throughout. All new components use `px`. Should do a pass to convert new component CSS to `rem` for consistency and font-size scaling.
- **Preview panel container styles** — The preview panels (BrowserPreview, TerminalOutput, DesktopPreview) may have been affected by the CSS changes — they look more rounded than the original design. Review `PreviewShell.module.css` and the preview components' CSS to ensure they match the original styling, not the new rounder aesthetic.
- **Content snippet throttling** — `UPDATE_CONTENT_SNIPPET` fires per-token. Should be throttled to 500ms in the callback, not just in the plan.
- **Agent activity view virtualization** — Long-running agents can accumulate 100+ activity log entries. Consider virtualized list rendering.
- **DesktopApp re-renders on every agent dispatch** — `useAgentState()` in the component body subscribes to the full agent tree. Consider splitting into a selector pattern or moving agent-dependent logic to child components.
- **Dual state updates** — Every browser snapshot, terminal event, etc. updates both global useState (simple chat mode) and per-agent reducer. Could consolidate to reducer-only once simple chat mode reads from root agent state.

### Bugs Found in Regression Testing (Not Yet Fixed)
- **Stop is cooperative and delayed** — Stop only takes effect between tool calls (`check_stop()` runs at tool boundaries). If an agent is mid-tool-call (e.g., browser navigating, code executing), the stop is delayed until the tool returns. Agent cards stay green (running) because the agents genuinely are still running. This is a pre-existing limitation, not a regression. Once the tool completes, the stop fires and `agent_completed(stopped)` events flow correctly. Phase 2 should consider `asyncio.Task.cancel()` for immediate stop.
- **Desktop opens as preview panel, not overlay** — Plan specified the user's desktop (header button) should open as a floating overlay. Currently it opens as a preview panel in the simple chat layout's middle column (existing behavior, not changed). Should be converted to an overlay/modal that appears on top of any view.
- **Resumed conversations don't restore agent network** — When resuming a past conversation that had sub-agents, the chat messages load but the agent network view doesn't appear. The frontend event replay (Task 11 frontend) is not yet wired up.

### Architecture
- **`final` event mechanism** — Fragile. The `final=true` flag on `AgentEvent` was used to close the server stream (`break` in `stream_events`). We removed the `break` to fix the root agent status bug, but the `final` concept is still confusing. The stream should end based on the producer completing (queue sends `None`), not a flag. Consider removing `_publish_final()` entirely and letting the stream close naturally.
- **Skill extraction removal** — Plan says to remove `skills/_extractor.py`, `skills/_registry.py`, `SkillsPanel`, `/api/skills` endpoints, `skill_extraction_loop`, `SkillAppliedPayload`, `_sub_agents.json`, and related ContextVars. Not yet done — deferred to avoid scope creep in the initial implementation.
- **`ContextUsagePayload` iteration fields** — Added `iteration` and `max_iterations` fields and threaded them through `ContextHook` → `ContextManager.record_response()`. This works but mixes iteration tracking (agent lifecycle concern) with token usage tracking (context management concern). Consider emitting iteration info from a separate event or the lifecycle events instead.

---

## Phase 2: Parallel Execution + Multi-Browser + Resource Isolation

### Design Principle: Concurrency Toggle

All parallel infrastructure is built and wired up, but actual concurrent execution is controlled by a config flag. When `parallel.enabled = false` (default), agent tool calls execute sequentially as today. When `true`, agent tool calls run in parallel via `asyncio.gather`. This lets us deploy the supporting work (browser pool, hook isolation, grounding fixes) safely and enable concurrency when ready.

```yaml
# config.yaml
parallel:
  enabled: false          # toggle concurrent agent execution
  max_concurrent: 4       # max simultaneous agent tool calls
```

### Task P2-1: Config

**Files:**
- `config/__init__.py` — Add `ParallelConfig` model:
  ```python
  class ParallelConfig(BaseModel):
      enabled: bool = False
      max_concurrent: int = 4
  ```
  Add to `AppConfig`: `parallel: ParallelConfig = Field(default_factory=ParallelConfig)`

- `config.yaml` — Add `parallel:` section with defaults

**Test:** Config loads correctly.

### Task P2-2: Hook isolation — per-agent state

Hooks with mutable state must not corrupt when multiple agents run in parallel. Each agent already gets its own hook instances via `default_hooks()` in `_agent_wrapper.py`, so sub-agents are isolated. But the root agent's hooks are shared across its tool loop iterations — if parallel agent tool calls trigger concurrent `before_tool`/`after_tool` callbacks on the root's hooks, state will corrupt.

**The risk:** When parallel tool calls run via `asyncio.create_task`, they all call `_run_tool_with_hooks()` which iterates the root's shared hook instances. Concurrent `before_tool`/`after_tool` calls on the same `LoopDetector` or `TurnRecorder` will corrupt their mutable state.

**Solution:** Add `asyncio.Lock` to hooks with mutable state. This is the correct fix — hooks continue to run normally for all tool calls (parallel or sequential), and the lock prevents concurrent corruption. Sub-agents already create their own hook instances via `default_hooks()` in `run_agent_as_tool`, so they're naturally isolated.

**Files:**
- `sdk/hooks/_loop_detector.py` — Add `self._lock = asyncio.Lock()`. Lock around `_current_round.append()` in `after_tool` and the finalization in `before_model`.
- `sdk/hooks/_budget_guard.py` — No lock needed. `before_model` runs sequentially between iterations (after all parallel tool calls complete), never concurrently.
- `sdk/hooks/_turn_recorder.py` — Replace `_tool_start_time` (single value) with `_tool_start_times: dict[str, float]` keyed by tool_call_id. Add lock around `_messages.append()` and `_total_tool_calls` increment.
- `sdk/hooks/_scratchpad_hook.py` — No change needed (stateless logging).
- Remove `sdk/hooks/_skill_tracking.py` — skill extraction is dropped.

**Note on sub-agent nesting:** Sub-agents can spawn their own sub-agents. Each level creates fresh hooks via `default_hooks()`, so nesting depth doesn't affect hook safety. The locks only matter for the specific agent whose tool loop is running parallel calls.

**Test:** Run two tool calls in parallel (with parallel.enabled=true), verify no hook state corruption.

### Task P2-3: Browser context pool

Replace the browser singleton with a pool that provides isolated `BrowserContext` instances per agent, seeded with the root profile's session state.

**Browser isolation model — copy-on-create:**
- The **root browser** continues to use `launch_persistent_context` with the default profile at `~/.computron_9000/browser/profiles/default/`. This preserves cookies, login sessions, localStorage across conversations.
- When a **sub-agent** needs a browser, the pool:
  1. Snapshots the root context's session state via `context.storage_state()` (exports cookies + localStorage as JSON)
  2. Launches a new ephemeral context on the same Chromium process via `browser.new_context(storage_state=snapshot)`
  3. The sub-agent inherits the root's login sessions, cookies, etc. but changes are isolated — if the sub-agent logs into something new, it doesn't affect the root or other agents
  4. When the sub-agent completes, the ephemeral context is closed and discarded

This gives us:
- **Session inheritance** — sub-agents can access sites the user is logged into
- **Isolation** — sub-agents can't corrupt the root profile or each other
- **Lightweight** — `new_context()` on an existing process is fast (~50ms), no new Chromium process needed
- **Concurrency** — each context has its own pages, cookies, downloads — fully independent

**Architecture change:**
- Currently: `get_browser()` returns a module-level singleton `_browser: Browser | None`
- New: `get_browser()` checks `get_current_agent_id()`:
  - Root agent (depth 0): returns the persistent singleton as before
  - Sub-agents: returns a pooled ephemeral `Browser` wrapper from `_agent_browsers: dict[str, Browser]`

**Files:**
- `tools/browser/core/browser.py`:
  - Keep `_browser` singleton for the root (persistent profile)
  - **Key refactor:** Currently `Browser.start()` calls `launch_persistent_context()` which creates the Chromium process AND context together (single API call). For the pool, we need to separate these:
    - `_launch_browser_process()` — calls `chromium.launch()`, returns a Playwright `Browser` object (the process)
    - Root context: `browser.new_context(storage_state=profile_path)` or keep `launch_persistent_context` for the root
    - Sub-agent contexts: `browser.new_context(storage_state=snapshot)` on the shared process
  - Add `Browser.start_ephemeral(playwright_browser, storage_state)` class method — creates a `Browser` wrapper around a `new_context()`
  - Add `_agent_browsers: dict[str, Browser] = {}` keyed by agent_id
  - Update `get_browser()` to route by agent_id:
    ```python
    async def get_browser() -> Browser:
        agent_id = get_current_agent_id()
        depth = get_current_depth()

        # Root browser: persistent singleton, lazy-initialized on first call
        # by ANY agent (root or sub-agent). This ensures cookies/profile
        # are always available for sub-agents to snapshot from.
        root = await _get_root_browser()

        if depth == 0:
            return root  # root agent uses persistent context directly

        # Sub-agent: ephemeral context seeded from root's session state
        if agent_id not in _agent_browsers:
            state = await root._context.storage_state()
            _agent_browsers[agent_id] = await Browser.start_ephemeral(
                _playwright_instance, storage_state=state)
        return _agent_browsers[agent_id]
    ```
  - The root persistent browser is always launched first (even if the root agent doesn't use it). This ensures sub-agents always have a profile to snapshot from. The root browser launch is the same lazy singleton as today — no behavior change for existing code.

- No separate pool class needed — the dict + lock lives inline in `browser.py`. `get_browser()` handles all routing.

- Cleanup: `context.close()` must happen in a `finally` block (not just on success) to handle agent errors. Wire into `agent_span()`'s finally or add cleanup in `_agent_wrapper.py`'s finally block. Ephemeral contexts are in-memory only — no disk cleanup needed.

**Downloads:** Each ephemeral context can be configured with a unique `downloads_path`. Downloaded files persist on disk (they're useful output), but the browser state itself is gone after `context.close()`.

**What sub-agents CAN do:** Navigate, click, fill forms, read pages, take screenshots — all on their own isolated pages with inherited cookies.

**What sub-agents CANNOT do:** Modify the root's persistent cookies, interfere with other agents' pages, or access each other's downloads.

**Test:**
1. Log into a site in the root browser
2. Spawn a sub-agent to browse that site — verify it has the login session
3. Spawn two sub-agents concurrently — verify they don't see each other's navigation
4. Verify root profile is unchanged after sub-agents complete

### Task P2-4: Parallel tool execution in the turn loop

The core change — run all tool calls in parallel when enabled.

**File:** `sdk/turn/_execution.py` lines 314-318

```python
# Current:
for tc in tool_calls:
    result = await _run_tool_with_hooks(tc, tools, hooks)
    history.append(result)

# New:
from config import load_config

parallel_cfg = load_config().parallel
if parallel_cfg.enabled and len(tool_calls) > 1:
    sem = asyncio.Semaphore(parallel_cfg.max_concurrent)
    async def _run_with_sem(tc):
        async with sem:
            return tc, await _run_tool_with_hooks(tc, tools, hooks)
    tasks = [asyncio.create_task(_run_with_sem(tc)) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.error("Parallel tool call failed: %s", result)
            # Can't recover tool_call_id from exception — log and skip
        else:
            tc, tool_result = result
            history.append(tool_result)
else:
    for tc in tool_calls:
        result = await _run_tool_with_hooks(tc, tools, hooks)
        history.append(result)
```

**Key details:**
- ALL tool calls run in parallel when enabled — no agent vs regular distinction
- `asyncio.create_task` copies ContextVars automatically in Python 3.12 — each parallel task gets its own context stack copy
- `Semaphore(max_concurrent)` limits concurrency
- When `parallel.enabled = false` (default), everything runs sequentially as before
- Hooks are thread-safe via `asyncio.Lock` (Task P2-2), so `_run_tool_with_hooks` works in parallel
- Sub-agents spawned by parallel tool calls each create their own hooks via `default_hooks()` — naturally isolated
- Sub-agents can nest further (agent → sub-agent → sub-sub-agent) — each level gets fresh hooks

**Test:** With `parallel.enabled: true`, send a message that triggers 2+ tool calls. Verify they run concurrently (check timestamps in logs). With `parallel.enabled: false`, verify sequential execution.

### Task P2-5: Grounding screenshot collision fix

**File:** `tools/_grounding.py` line 53, 79, 82

Use `get_current_agent_id()` in the screenshot filename:

```python
from sdk.events import get_current_agent_id

async def run_grounding(screenshot_bytes, task, *, screenshot_filename=None):
    if screenshot_filename is None:
        agent_id = get_current_agent_id() or "default"
        safe_id = agent_id.replace(".", "_")
        screenshot_filename = f"grounding_{safe_id}.png"
    # ... rest unchanged
```

**Test:** Two agents calling `run_grounding()` simultaneously don't overwrite each other's screenshots.

### Task P2-6: Desktop display pool

Enable multiple desktop agents with separate virtual displays.

**Files:**
- `tools/desktop/_lifecycle.py` — Parameterize `start_desktop(display=":99")`:
  - Replace hardcoded `:99` in `_START_DESKTOP_CMD` with dynamic display parameter
  - VNC port derived from display: `6080 + (display_num - 99)`

- `tools/desktop/_exec.py` — Already parameterized (`display: str = ":99"`)

- `agents/desktop/agent.py` — Remove hardcoded `DISPLAY=:99` from system prompt examples (lines 67-73). Replace with plain commands like `run_bash_cmd("wmctrl -l")`. The display routing is handled transparently by the tools — the agent never needs to know its display number.

- `config/__init__.py` — Add to `DesktopConfig`:
  ```python
  user_display: str = ":99"      # user's personal desktop
  agent_display_base: int = 100   # agents start from :100
  ```

- Display allocation is a simple counter + dict in `_lifecycle.py` (no separate pool class needed):
  ```python
  _next_display: int = 100
  _active_displays: dict[str, int] = {}  # agent_id -> display number
  ```

- `container/entrypoint.sh` — Start only the user's desktop (`:99`), not agent desktops

- Desktop tools (`read_screen`, `click_element`, `keyboard_type`, etc.) — these use `_run_desktop_cmd()` which already accepts a `display` parameter. Add a `_current_display` ContextVar that gets set when allocating a display. `_run_desktop_cmd()` reads from the ContextVar instead of defaulting to `:99`. The agent never knows its display number — tools handle routing transparently.

- `run_bash_cmd` does NOT need display awareness — desktop operations should use the dedicated desktop tools, not raw bash with DISPLAY prefix.

**Test:** Two desktop agents each get their own display. Tools automatically route to the correct display.

### Task P2-7: Agent task registry — DEFERRED

Per-agent cancellation (stop one agent without stopping all). Needs UI work (cancel button per agent card) and `asyncio.Task` tracking. Current `request_stop()` stops everything, which is sufficient for now. Revisit when users ask for granular control.

### Task P2-8: Frontend updates

Phase 1 UI already handles multiple running agents (keyed by `agent_id`). Additional work:

- Multiple pulsing status dots (already works — `@keyframes pulse` on `.running`)
- Agent cards updating independently during streaming (already works — reducer dispatches by `agent_id`)
- `useStreamingChat` segmentation — already routes by `agent_id` not just `depth`

Main change: ensure interleaved events from parallel agents don't break the stream reader. The `_handleStreamEvent` function processes each event independently by `agent_id`, so this should work without changes.

**Test:** With parallel enabled, send a task that spawns 3 agents. Verify all 3 cards appear, stream independently, and show correct status on completion.

### Implementation Order

1. **P2-1** Config + marker (foundation, no behavior change)
2. **P2-5** Grounding fix (simple, prevents file collisions)
3. **P2-3** Browser pool (major refactor, needed before parallel)
4. **P2-2** Hook isolation (verify existing isolation is sufficient)
5. **P2-4** Parallel execution (the big one — gated by config flag)
6. **P2-6** Desktop display pool (optional, only needed for parallel desktop agents)
7. **P2-7** Agent task registry (optional, for per-agent cancellation)
8. **P2-8** Frontend verification (should work with no changes)

---

## Key Design Decisions

1. **Chat is root-only** — the user interacts exclusively with the root agent. Sub-agent output never appears in chat. Sub-agents are observed through the agent network's activity view.
2. **Agent IDs reuse the existing `context_id` format** — the hierarchical dotted format (`root.browser_agent.3`) naturally encodes lineage. No new ID scheme needed.
3. **Lifecycle events emit from `agent_span()`** — the single chokepoint all agents pass through, so no agent can be missed.
4. **Agent state reducer lives in React Context**, separate from `useStreamingChat`. The streaming hook routes root events to chat messages and sub-agent events to the agent state reducer.
5. **Per-agent activity logs and previews from the start** — the state model stores per-agent activity, screenshots, terminal, etc. even in Phase 1 (one active agent at a time), so Phase 2 requires zero frontend state model changes.
6. **Only agent tools parallelize** — regular tools (file writes, bash) stay sequential to avoid filesystem race conditions without complex locking.
7. **Browser multi-context uses Playwright's native `browser.new_context()`** — one Chromium process, many contexts. Memory-efficient and natively supported.
8. **Shared components** — `MarkdownContent` extracted from Message.jsx into its own module, shared by both main chat and agent activity views. `formatAgentName` shared from AgentCard. `mergeTerminalEvent` and `formatElapsed` shared from `utils/agentUtils.js`.
9. **Multi-turn forest** — each conversation turn creates a new root agent. The network graph renders a forest (multiple disconnected trees) by finding all root agents and BFS from each.
10. **Skill extraction dropped** — dead end. Agent events are the better foundation for any future learning/reuse system.

---

## Verification

### Phase 1 — Tested and Verified ✓
1. `just test` — 235 SDK tests pass
2. UI build passes (`npx vite build`)
3. Manual testing with Playwright:
   - ✓ Simple chat (no sub-agents) — no agent network shown
   - ✓ Dark/light mode toggle works correctly
   - ✓ Sidebar flyout panels open/close, settings render flat
   - ✓ New conversation resets state
   - ✓ Browser agent — network shows 2 agents with connector line, sub-agent card with thumbnail
   - ✓ Coder agent — terminal preview with output, file output
   - ✓ Expanded view — instruction, thinking (matching main chat style), markdown content, tool call badges, browser/terminal preview, back button, nudge bar
   - ✓ Agent status transitions (running → complete/success)
   - ✓ Multi-turn — turn 1 simple chat, turn 2 spawns sub-agent, all 3 agents visible in network graph

### Phase 2
4. Test parallel execution: send a message that triggers 2+ agent tool calls simultaneously
5. Verify separate browser sessions (different URLs in different agent cards)
6. Verify desktop pool works with multiple desktop agents
7. Verify cancellation propagates to all parallel agents
