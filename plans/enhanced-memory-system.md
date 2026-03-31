# Enhanced Memory System

Plan by Claude (Opus 4.6), based on review of PR #9 (TA-Mem) and analysis of the current memory architecture.

## Problem

The current memory system has two scaling issues:

1. **Every memory is injected into the system prompt every turn.** `_refresh_system_message()` in `message_handler.py` calls `load_memory()`, formats every entry as `key: value`, and prepends it to the system prompt. This works fine at 10 memories, becomes wasteful at 50, and actively harmful at 200+ — eating context window for memories that aren't relevant to the current conversation.

2. **No query capability.** The agent can only `remember(key, value)` and `forget(key)`. If the user asks "what did I tell you about my project last week?", the agent has to scan the full memory dump in its context. There's no way to search by content, time, or topic.

PR #9 (TA-Mem) had good ideas for solving #2 — multi-strategy queries, timeframe parsing, tag extraction — but introduced heavy unused dependencies (`scikit-learn`), a parallel storage format that conflicts with `memory.py`, and homegrown "semantic embeddings" (character bigram hashing) that don't actually capture meaning.

This plan keeps the good parts and fixes the problems.

## Design Principles

- **One storage format, one file.** Extend `MemoryEntry`, don't create a parallel system.
- **No new production dependencies.** Use stdlib + Ollama (already a dep) for everything.
- **Lazy migration.** Backfill new fields on write, not on import.
- **One query tool for the agent.** `recall(query)` does the right thing automatically. The LLM shouldn't have to choose between 4 query strategies.
- **Decouple memory from context injection.** The agent gets a summary/subset of memories, not the full dump.

## Changes

### 1. Extend `MemoryEntry` with timestamps and tags

**File**: `tools/memory/memory.py`

Add three fields to the existing dataclass:

```python
@dataclass
class MemoryEntry:
    value: str
    hidden: bool = False
    created_at: str = ""      # ISO timestamp
    updated_at: str = ""      # ISO timestamp
    tags: list[str] = field(default_factory=list)
```

**Migration**: In `_load_raw()`, entries missing `created_at` get it set to `""`. In `remember()`, always set `updated_at = now()` and backfill `created_at` if empty. Tags are extracted on write via `_extract_tags()`. No bulk migration step — entries get upgraded as they're touched.

**Backward compat**: `_load_raw()` already handles dicts with just `value`/`hidden`. The new fields have defaults, so old JSON deserializes fine. `_save_raw()` writes the new fields, so the file upgrades over time.

### 2. Add tag extraction (lightweight, no deps)

**File**: `tools/memory/memory.py` (add internal helper)

Port the `_extract_tags()` logic from the PR — it's the right approach:
- Extract CamelCase and snake_case terms
- Find frequent non-stop-words
- Score and return top 5 tags
- Called in `remember()` on every write

This is ~60 lines, stdlib only (`re`, `collections.Counter`).

### 3. Add `recall()` — single smart query tool

**File**: `tools/memory/memory.py` (or new `tools/memory/_query.py` if `memory.py` gets too long)

```python
async def recall(query: str) -> dict[str, object]:
    """Search memories by keywords, tags, and timeframes."""
```

This replaces the four separate query tools from PR #9 (`query_memory_by_key`, `query_memory_by_semantic`, `query_memory_by_timeframe`, `query_memory_smart`) with one tool that auto-detects intent. The LLM doesn't need to decide which query strategy to use — `recall()` figures it out from the query text.

#### Examples of what the agent can call

```python
# Direct key lookups
recall("user_timezone")          # exact key match → returns the entry
recall("api_key")                # key match → "api_key_stripe", "api_key_openai", etc.

# Time-based queries
recall("last week")              # everything created/updated in the past 7 days
recall("what did I say yesterday")  # "yesterday" triggers timeframe filter
recall("memories from January")  # month-name detection
recall("past 3 days")            # relative day count

# Keyword/topic searches
recall("python projects")        # keyword match on values + tags
recall("what ML projects am I working on")  # stop words stripped, "ML" + "projects" matched
recall("API keys")               # matches keys and values containing "API" and "keys"
recall("meeting notes")          # tag match on memories tagged ["meeting", "notes"]

# Mixed intent (multiple strategies fire)
recall("python project from last week")  # timeframe + keyword, results merged
recall("user_name")              # exact key hit + keyword search, key match ranked first
```

#### Strategy router

Adapted from TA-Mem's `query_memory_smart`, but simplified — strategies run in order and results are merged:

**Strategy 1 — Exact key match** (score: 1.0):
If the query looks like a key (single token, matches `[a-z_]+` pattern), check for an exact match in the store. Also check for prefix matches — `recall("api_key")` should surface `api_key_stripe` and `api_key_openai`. Exact match scores 1.0, prefix matches score 0.9.

**Strategy 2 — Timeframe filter** (score: 0.8):
If the query contains time patterns (`last week`, `yesterday`, `past N days`, `in January`, `today`, `this month`, `recent`), parse the timeframe into a `(start, end)` datetime range and filter memories whose `created_at` or `updated_at` falls within it. All timeframe-matched results get a base score of 0.8. Port the parsing logic from the PR, with these cleanups:
- Remove the separate "last week" (calendar week) vs "last 1 week" (rolling 7 days) paths — just use rolling 7 days for both
- Drop the "yester day" alternative spelling
- Handle "past X" by normalizing to "last X" instead of a recursive call

**Strategy 3 — Keyword + tag search** (score: varies):
Always runs unless strategies 1+2 already returned enough results (≥10). This is the workhorse for natural language queries:

1. Tokenize the query: split on whitespace and punctuation, lowercase, remove stop words
2. For each memory, compute a relevance score:
   - **Value substring match**: +0.3 per query token found as a substring in the memory value (case-insensitive). If the full query string appears as a contiguous substring, +0.5 bonus.
   - **Tag overlap**: +0.2 per query token that matches a tag exactly. Tags are already lowercase single words, so this is a set intersection.
   - **Key name match**: +0.2 per query token found in the key name (split on `_`). This lets `recall("timezone")` find `user_timezone`.
3. Only include memories with score > 0 (at least one token matched something)

#### Scoring and ranking

Each strategy assigns a score between 0.0 and 1.0 to its results. When a memory appears in multiple strategies, its scores are combined:

```python
# If "user_timezone" is found by both exact key (1.0) and keyword (0.2):
# final score = max(1.0, 0.2) = 1.0 (take the best, don't stack)
#
# If a memory matches both timeframe (0.8) and keywords (0.5):
# final score = max(0.8, 0.5) + 0.1 = 0.9 (multi-strategy bonus)
```

The multi-strategy bonus (+0.1, capped at 1.0) rewards memories that match on multiple dimensions — a memory about "Python" from "last week" should rank higher than one that only matches the timeframe when the query is `recall("python project from last week")`.

Final results are:
1. Deduplicated by key (keep highest-scoring entry)
2. Sorted by score descending
3. Capped at 10 results
4. `hidden` memories are **included** in results — the hidden flag only controls UI visibility, not agent access

#### Return format

```python
{
    "status": "ok",
    "query": "python projects from last week",
    "strategies": ["timeframe", "keyword"],   # which strategies contributed results
    "count": 3,
    "results": [
        {
            "key": "project_ml",
            "value": "Working on Python ML classifier for fraud detection",
            "score": 0.9,           # timeframe(0.8) + multi-strategy bonus
            "match_type": "timeframe+keyword",
            "tags": ["python", "project", "machine", "learning"],
            "created_at": "2026-03-25T14:30:00",
            "updated_at": "2026-03-28T09:15:00",
        },
        {
            "key": "python_version",
            "value": "Using Python 3.12 for all new projects",
            "score": 0.5,           # keyword only
            "match_type": "keyword",
            "tags": ["python", "version"],
            "created_at": "2026-03-01T10:00:00",
            "updated_at": "2026-03-01T10:00:00",
        },
        ...
    ]
}
```

#### Why one tool instead of four

PR #9 exposed `query_memory_by_key`, `query_memory_by_semantic`, `query_memory_by_timeframe`, and `query_memory_smart` as separate tools. This has two problems:

1. **Tool budget**: Every tool registered with the agent costs tokens in the system prompt (for the tool schema) and decision overhead (the LLM must choose which to call). Four query tools that could be one is wasteful.
2. **Wrong abstraction level**: The agent shouldn't need to know whether its query is "semantic" or "temporal" — that's an implementation detail. The agent knows what it wants to find; `recall()` figures out how.

### 4. Move from full-dump to selective context injection

**File**: `server/message_handler.py`

This is the most impactful change. Currently, `_refresh_system_message()` runs before every model invocation (line 223 in `message_handler.py`, inside `_run_turn()`). It calls `load_memory()`, formats **every** entry as `  key: value`, and prepends the whole block to the system prompt:

```python
# Current implementation (lines 124-138)
def _refresh_system_message(history: ConversationHistory, system_prompt: str) -> None:
    instruction = system_prompt
    memory = load_memory()
    if memory:
        lines = "\n".join(f"  {k}: {e.value}" for k, e in memory.items())
        sep = "─" * 64
        memory_block = (
            f"\n── Memory (persisted across sessions) "
            f"──────────────────────────\n{lines}\n{sep}\n"
        )
        instruction = memory_block + instruction
    history.set_system_message(instruction)
```

Every key-value pair goes into the system message regardless of relevance. At 10 memories this is fine. At 100 memories with long values, this can burn thousands of tokens per turn on content the agent never looks at.

#### The two-tier approach

**Tier 1 — Always in context (pinned memories)**:
- Memories with `pinned: True` (new field on `MemoryEntry`)
- Memories updated in the last 24 hours (freshly stored = likely relevant)
- Auto-pinned by key prefix convention: `user_*`, `pref_*`, `config_*`
- Hard cap at `max_entries` (default 20) to bound context usage

**Tier 2 — Available via `recall()` tool**:
- Everything else
- The agent is told how many additional memories exist so it knows to use `recall()` when it needs something not in context

#### What the agent sees — before and after

**Before** (current, every memory dumped):
```
── Memory (persisted across sessions) ──────────────────────────
  user_timezone: America/Chicago
  user_name: Larry
  project_x_api_key: sk-...
  random_fact_42: The capital of Bhutan is Thimphu
  old_meeting_notes: We discussed the Q3 roadmap and decided to...
  ... (50 more entries) ...
────────────────────────────────────────────────────────────────
```

**After** (selective injection):
```
── Memory (persisted across sessions) ──────────────────────────
  user_timezone: America/Chicago
  user_name: Larry
  project_x_api_key: sk-...
  (47 more memories available — use recall(query) to search)
────────────────────────────────────────────────────────────────
```

The agent still sees its most important memories immediately. For everything else, it has a tool.

#### Selection logic

New function in `tools/memory/memory.py` (not in `message_handler.py` — keep memory logic with memory code):

```python
_AUTO_PIN_PREFIXES = ("user_", "pref_", "config_")

def select_context_memories(
    entries: dict[str, MemoryEntry],
    max_entries: int = 20,
) -> tuple[dict[str, MemoryEntry], int]:
    """Select memories for system prompt injection.

    Args:
        entries: All loaded memories.
        max_entries: Maximum entries to include in context.

    Returns:
        Tuple of (selected memories dict, count of remaining memories).
    """
```

Selection priority (each step fills remaining slots):

1. **Pinned memories** — `entry.pinned is True`, always included regardless of cap. These are memories the user or agent has explicitly marked as "always show me this." Also includes keys matching `_AUTO_PIN_PREFIXES`.
2. **Recent memories** — `entry.updated_at` within the last 24 hours. If you just stored a memory this session, it should be visible immediately without needing `recall()`.
3. **Backfill** — remaining slots filled by most recently updated entries. This means older but frequently-updated memories stay visible longer than stale ones.

If pinned memories alone exceed `max_entries`, all pinned memories are still included (the cap is soft for pinned). This prevents a situation where pinning a memory makes it disappear.

#### Changes to `_refresh_system_message()`

```python
def _refresh_system_message(history: ConversationHistory, system_prompt: str) -> None:
    instruction = system_prompt
    all_memory = load_memory()
    if all_memory:
        selected, remaining = select_context_memories(all_memory)
        lines = "\n".join(f"  {k}: {e.value}" for k, e in selected.items())
        if remaining > 0:
            lines += f"\n  ({remaining} more memories available — use recall(query) to search)"
        sep = "─" * 64
        memory_block = (
            f"\n── Memory (persisted across sessions) "
            f"──────────────────────────\n{lines}\n{sep}\n"
        )
        instruction = memory_block + instruction
    history.set_system_message(instruction)
```

The only change is swapping `load_memory()` → `select_context_memories(load_memory())` and appending the "N more available" hint. The rest of the function stays the same.

#### Fallback behavior

When total memories <= `max_entries`, `select_context_memories()` returns all of them and `remaining = 0`. The hint line doesn't appear. This means **existing behavior is preserved exactly** for small memory stores — the change only kicks in once the store grows past the threshold.

#### Why not summarize?

An alternative to selective injection is to LLM-summarize all memories into a compact paragraph. This was considered and rejected because:
- It requires an LLM call on every turn (adds latency, uses Ollama capacity)
- Summaries lose key names, which the agent needs for `forget()` and updates
- The two-tier approach is simpler, deterministic, and zero-cost

### 5. Update agent system prompt

**File**: `agents/computron/agent.py`

Change the MEMORY documentation line from:

```
MEMORY — remember(key, value) / forget(key). Store user preferences proactively.
```

To:

```
MEMORY — remember(key, value) / forget(key) / recall(query).
  remember: Store user preferences, facts, and context proactively.
  forget: Remove a memory by key.
  recall: Search memories by keyword, tag, or timeframe.
    Examples: recall("API keys"), recall("last week"), recall("python projects")
  Pinned memories appear in your context automatically.
  Use recall() for everything else — don't assume you have all memories visible.
```

### 6. Add `pinned` field — backend, API, and UI

Pinning is controllable from both the agent (via tools) and the user (via the UI), following the same pattern as the existing `hidden` toggle.

#### 6a. Data model

**File**: `tools/memory/memory.py`

```python
@dataclass
class MemoryEntry:
    value: str
    hidden: bool = False
    pinned: bool = False      # Always include in agent context
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
```

Add a `set_pinned()` function mirroring the existing `set_key_hidden()`:

```python
def set_pinned(key: str, pinned: bool) -> None:
    """Mark a memory key as pinned or unpinned for context injection."""
    data = _load_raw()
    if key in data:
        data[key].pinned = pinned
        _save_raw(data)
```

Agent tools:
- `pin_memory(key)` / `unpin_memory(key)` — the agent can pin memories it thinks should stay in context
- Auto-pin memories whose keys match common patterns: `user_*`, `pref_*`, `config_*`

#### 6b. API endpoint

**File**: `server/aiohttp_app.py`

Add `POST /api/memory/{key}/pinned` — mirrors the existing `POST /api/memory/{key}/hidden` endpoint:

```python
async def set_memory_pinned_handler(request: Request) -> Response:
    """Set the pinned flag for a memory entry."""
    key = request.match_info["key"]
    if key not in load_memory():
        return web.json_response({"error": f"Memory key '{key}' not found"}, status=404)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    set_pinned(key, bool(body.get("pinned", False)))
    return web.Response(status=204)
```

Register the route alongside the existing memory routes:

```python
web.post("/api/memory/{key}/pinned", set_memory_pinned_handler),
```

Update `GET /api/memory` to include pinned keys in the response:

```python
async def list_memory_handler(_request: Request) -> Response:
    entries = load_memory()
    return web.json_response({
        "entries": {k: e.value for k, e in entries.items()},
        "hidden": sorted(k for k, e in entries.items() if e.hidden),
        "pinned": sorted(k for k, e in entries.items() if e.pinned),  # NEW
    })
```

#### 6c. Frontend — MemoryPanel

**File**: `server/ui/src/components/MemoryPanel.jsx`

Follow the exact pattern used for `hiddenKeys`. The hidden toggle currently works as:
1. `hiddenKeys` state (a `Set`) populated from `data.hidden` in the `onFetched` callback
2. `toggleHidden(key)` does an optimistic local state update, POSTs to `/api/memory/{key}/hidden`, reverts on error
3. Renders an `<EyeIcon slashed={isHidden} />` button with `styles.eyeBtn` / `styles.eyeBtnActive`

Add the same for pinned:

**State**:
```jsx
const [pinnedKeys, setPinnedKeys] = useState(new Set());

const onFetched = useCallback((data) => {
    if (Array.isArray(data.hidden)) setHiddenKeys(new Set(data.hidden));
    if (Array.isArray(data.pinned)) setPinnedKeys(new Set(data.pinned));  // NEW
}, []);
```

**Toggle handler** (same optimistic-update-with-revert pattern as `toggleHidden`):
```jsx
const togglePinned = async (key) => {
    const nowPinned = !pinnedKeys.has(key);
    setPinnedKeys((prev) => {
        const next = new Set(prev);
        if (nowPinned) next.add(key); else next.delete(key);
        return next;
    });
    try {
        await fetch(`/api/memory/${encodeURIComponent(key)}/pinned`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned: nowPinned }),
        });
    } catch (_) {
        setPinnedKeys((prev) => {
            const next = new Set(prev);
            if (nowPinned) next.delete(key); else next.add(key);
            return next;
        });
    }
};
```

**Rendering** — add a pin button next to the existing eye button in the `itemActions` div:
```jsx
<div className={styles.itemActions}>
    <button
        className={`${styles.pinBtn}${isPinned ? ` ${styles.pinBtnActive}` : ''}`}
        onClick={() => togglePinned(key)}
        title={isPinned ? 'Unpin from agent context' : 'Pin to agent context'}
    >
        <PinIcon size={12} filled={isPinned} />
    </button>
    <button
        className={`${styles.eyeBtn}${isHidden ? ` ${styles.eyeBtnActive}` : ''}`}
        onClick={() => toggleHidden(key)}
        title={isHidden ? 'Show value' : 'Hide value'}
    >
        <EyeIcon size={12} slashed={isHidden} />
    </button>
    {/* delete button */}
</div>
```

**Tooltips explain what pinning does**: "Pin to agent context" / "Unpin from agent context" — makes it clear this controls whether the agent sees the memory in its prompt, not just a visual preference.

#### 6d. PinIcon component

**File**: `server/ui/src/components/icons/PinIcon.jsx`

New SVG icon component following the same pattern as `EyeIcon`. Props: `size` and `filled` (boolean). Unfilled = outline pin, filled = solid pin. A simple thumbtack/pushpin shape.

#### 6e. Styles

**File**: `server/ui/src/components/CustomToolsPanel.module.css`

Add pin button styles mirroring the existing eye button styles:

```css
.pinBtn {
    /* same base styles as .eyeBtn */
}

.pinBtnActive {
    color: var(--accent);    /* highlight color when pinned, unlike eyeBtn which dims */
    opacity: 1;
}
```

Pinned memories could also get a subtle visual indicator on the list item itself — a small accent-colored left border or a pin icon next to the key name — so the user can scan which memories are pinned without hovering over buttons.

#### 6f. Sort order

Pinned memories should sort to the top of the memory list in the UI, so users can see at a glance which memories are always in the agent's context. Within the pinned group, sort alphabetically by key. Unpinned memories follow, also alphabetical.

### 7. All agents get memory tools

**Currently**: Only the root agent (COMPUTRON) has `remember` and `forget` in its tool list. Sub-agents and specialized agents (browser, computer, desktop, media) have no memory access — they can't read or write memories, and their conversation history doesn't include the memory block.

**Change**: All agents get `recall` (read access to shared memory). Only the root agent (COMPUTRON) gets write tools (`remember`, `forget`, `pin_memory`, `unpin_memory`) to start. Memory is **shared, not scoped per-agent**.

#### Why shared memory

- The memory store holds user-level facts (name, timezone, preferences, API keys). Every agent benefits from these — the browser agent knowing the user's preferred language matters just as much as the root agent knowing it.
- Per-agent scoping adds complexity (what's the scope key? `agent_name`? `context_id`? what about renamed agents?) for a problem that doesn't exist yet. If it becomes a problem, namespaced keys (`browser:login_flow_github`) solve it without infrastructure changes.

#### Why COMPUTRON is the only writer (for now)

- COMPUTRON orchestrates all other agents. It decides what's worth persisting based on the full conversation context.
- Specialized agents are focused on execution (browse this page, run this code). Having them also decide what to remember adds decision overhead to agents that should be doing one thing well.
- Avoids conflicting writes — two agents independently remembering different values for the same key in the same turn would be a race condition.
- This can be relaxed later. If the browser agent consistently discovers things worth persisting (site login flows, cookie requirements), giving it `remember` is a one-line tool list change.

#### What changes per agent type

**Root agent (COMPUTRON_9000)** — `agents/computron/agent.py`:
- Already has `remember`, `forget`. Add `recall`, `pin_memory`, `unpin_memory`.
- System prompt updated as described in section 5.

**Browser agent** — `agents/browser/agent.py`:
- Add `recall` to its tool list.
- Add to its system prompt: `MEMORY — recall(query) to look up stored user preferences, site behaviors, and context.`
- Receives pinned memories in its context block (via `_refresh_system_message` or equivalent).

**Computer agent** — `agents/computer/agent.py`:
- Add `recall` to its tool list.
- Add to its system prompt: `MEMORY — recall(query) to look up stored project config, build patterns, and environment details.`
- Receives pinned memories in its context block.

**Desktop agent** — `agents/desktop/agent.py`:
- Add `recall` to its tool list.
- Add to its system prompt: `MEMORY — recall(query) to look up stored application preferences and workflow patterns.`
- Receives pinned memories in its context block.

**Media agent** — `agents/media/agent.py`:
- Add `recall` to its tool list.
- Add to its system prompt: `MEMORY — recall(query) to look up stored style preferences and generation parameters.`
- Receives pinned memories in its context block.

**Sub-agents** — `agents/sub_agent/agent.py`:
- Add `recall` to their tool list.
- Currently sub-agents build a fresh `ConversationHistory` with only their system prompt (no memory block). Fix: call `select_context_memories()` and prepend pinned memories to the sub-agent's system message, same as the root agent gets.
- Sub-agent system prompt gets a one-liner about memory availability.

#### Context injection: every agent gets memories automatically

Every agent has a turn loop — the question is whether we inject memories into all of them, or have the root agent pass down what it thinks each sub-agent needs.

**Decision: inject into every agent's turn loop.** Reasons:

- **Simpler.** No new parameter on `run_sub_agent()`, no logic in COMPUTRON to decide what to pass down. Every turn loop calls `_refresh_system_message()` — that function already handles selection via `select_context_memories()`. Just make sure all agent turn loops use it.
- **Cheaper than it sounds.** Pinned memories are capped at ~20 short entries. That's a handful of lines in the system prompt — negligible compared to the tool schemas and agent instructions already there.
- **Pass-down requires predicting the future.** If COMPUTRON has to decide what memories to give the browser agent before it runs, it'll sometimes get it wrong. The browser agent might need `user_timezone` to interpret a date on a page, but COMPUTRON had no way to know that in advance. Auto-injection means the agent always has what it needs.
- **`recall()` is self-service.** For anything not pinned, the sub-agent can call `recall()` itself if it hits a gap. No round-trip back to COMPUTRON needed.

**Implementation**: The turn loop already calls `_refresh_system_message(history, agent.instruction)` for the root agent. The same call needs to happen in every agent's turn entry point. Since all agents go through `run_turn()` in the SDK, the cleanest approach is to wire `_refresh_system_message()` (or an equivalent memory-injection hook) into `run_turn()` itself, so it happens automatically for every agent without each agent file needing to opt in.

## Phase 2 (future, not this PR)

### Ollama embeddings for real semantic search

Once the memory store grows large enough that keyword search isn't sufficient (~500+ entries), add optional embedding-based search:

- Use `ollama.embed()` with `nomic-embed-text` (small, fast)
- Store embedding vectors in a separate sidecar file (`memory_embeddings.json`) to keep the main file lean
- Add as a strategy in `recall()` — only runs if embeddings are available
- Zero new deps (Ollama is already required)

### Memory categories / namespaces

Group memories by namespace (`user:name`, `project:api_key`, `fact:bhutan_capital`) to enable bulk operations and better context selection.

## Implementation Order

1. Extend `MemoryEntry` with `created_at`, `updated_at`, `tags`, `pinned` fields
2. Add `_extract_tags()` helper
3. Update `remember()` to populate new fields on write
4. Add timeframe parsing helpers (port from PR #9, clean up edge cases)
5. Implement `recall()` with keyword + tag + timeframe strategies
6. Add `pin_memory()` / `unpin_memory()` tools and `set_pinned()` backend function
7. Add `POST /api/memory/{key}/pinned` endpoint, update `GET /api/memory` response
8. Add `PinIcon` component, pin toggle in `MemoryPanel.jsx`, styles
9. Refactor `_refresh_system_message()` to use `select_context_memories()`
10. Register `recall` in all agent tool lists (browser, computer, desktop, media, sub-agent)
11. Register write tools (`remember`, `forget`, `pin_memory`, `unpin_memory`) in COMPUTRON only
12. Update system prompts for all agents
13. Inject pinned memory block into sub-agent and specialized agent context
14. Tests for all of the above

## Files Affected

| File | Change |
|------|--------|
| `tools/memory/memory.py` | Extend `MemoryEntry`, add `_extract_tags`, `recall`, `pin_memory`, `unpin_memory`, `set_pinned` |
| `tools/memory/__init__.py` | Export new public functions |
| `server/message_handler.py` | Refactor `_refresh_system_message()` to use selective injection |
| `server/aiohttp_app.py` | Add `POST /api/memory/{key}/pinned` endpoint, update `GET /api/memory` response |
| `server/ui/src/components/MemoryPanel.jsx` | Add `pinnedKeys` state, `togglePinned` handler, pin button in item actions, sort pinned to top |
| `server/ui/src/components/icons/PinIcon.jsx` | New thumbtack/pushpin SVG icon component |
| `server/ui/src/components/CustomToolsPanel.module.css` | Add `.pinBtn` / `.pinBtnActive` styles |
| `agents/computron/agent.py` | Update system prompt, register `recall`, `pin_memory`, `unpin_memory` |
| `agents/browser/agent.py` | Add `recall` to tools, update system prompt |
| `agents/computer/agent.py` | Add `recall` to tools, update system prompt |
| `agents/desktop/agent.py` | Add `recall` to tools, update system prompt |
| `agents/media/agent.py` | Add `recall` to tools, update system prompt |
| `agents/sub_agent/agent.py` | Add `recall` to tools, inject pinned memories into context |
| `tests/tools/test_memory.py` | Tests for new fields, tag extraction, recall, pinning, context selection |

## What This Doesn't Do

- No new production dependencies
- No parallel storage format
- No homegrown embeddings pretending to be semantic search
- No auto-migration on import (entries upgrade lazily on write)
- No plan documents cluttering the repo root (this file lives in `plans/`)
