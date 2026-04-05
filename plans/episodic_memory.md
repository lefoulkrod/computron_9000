# Episodic Memory: Search Past Conversations

## Context

COMPUTRON's memory system has a gap: long-term facts persist via `remember(key, value)`, and session-local data lives in the scratchpad, but there's no way to recall context from **past conversations**. If the user discussed a scraping script last week but nobody explicitly `remember()`'d it, that context is gone. Episodic memory closes this gap by automatically summarizing conversations and making them searchable via a tool call.

## Design

Two components:

1. **Background indexer** — an async loop that runs alongside the app, periodically scanning conversations and generating summaries for any that are new or updated. Stores an index file at `~/.computron_9000/episodic_index.json`.

2. **Search tool** — `search_conversations(query)` that the agent calls when it needs context from past sessions. Loads the index, scores matches via token overlap, returns top results.

The indexer is decoupled from the request path — no hooks into `message_handler.py`. It backfills old conversations naturally and if it falls behind, search just returns slightly stale results.

## Implementation

### Step 1: Config — `config/__init__.py`

Add `EpisodicConfig` and wire it into `AppConfig`:

```python
class EpisodicConfig(BaseModel):
    """Configuration for episodic memory (past conversation search)."""
    enabled: bool = True
    poll_interval: int = 60  # seconds between index scans
    min_turns: int = 3       # skip conversations shorter than this
```

Add to `AppConfig`:
```python
episodic: EpisodicConfig = Field(default_factory=EpisodicConfig)
```

### Step 2: Expose `_serialize_messages` — `sdk/context/_strategy.py`

Rename `_serialize_messages` to `serialize_messages` (public). Add it to `sdk/context/__init__.py` exports. The episodic indexer needs this to convert message history into text for summarization.

Update all internal references (there should only be one call site within the compaction strategy itself).

### Step 3: Episodic index model and persistence — `tools/episodic/episodic.py`

New file. Contains:

- **`EpisodicRecord`** (Pydantic model):
  ```
  conversation_id: str
  title: str
  started_at: str          # ISO timestamp
  turn_count: int
  summary: str             # the conversation summary text
  indexed_at: str          # ISO timestamp of when this record was created
  ```

- **`_index_path() -> Path`** — returns `~/.computron_9000/episodic_index.json`

- **`load_index() -> list[EpisodicRecord]`** — loads the index file, returns empty list if missing

- **`save_index(records: list[EpisodicRecord]) -> None`** — atomic write (tmp + rename, matching `_store.py` pattern)

- **`remove_from_index(conversation_id: str) -> None`** — removes a record by conversation ID (for cleanup on delete)

### Step 4: Indexer — `tools/episodic/_indexer.py`

New file. The background worker logic:

- **`async def index_new_conversations() -> None`**
  - Calls `list_conversations()` to get all conversations
  - Loads the current index via `load_index()`
  - Builds a set of already-indexed conversation IDs with their turn counts
  - For each conversation not in the index (or with a higher turn count than when last indexed):
    - Skip if `turn_count < config.episodic.min_turns`
    - Call `_summarize_conversation(conversation_id)` to generate a summary
    - Append/update an `EpisodicRecord`
  - Save the updated index

- **`async def _summarize_conversation(conversation_id: str) -> str`**
  - First check for existing `SummaryRecord` entries via `list_summary_records(conversation_id)`. If any exist, use the latest `summary_text` — no LLM call needed.
  - Otherwise, load the history via `load_conversation_history(conversation_id)`, serialize via `serialize_messages()`, and call the summary LLM using the same pattern as `_title_generation.py` (load config, get provider, call `provider.chat` with `_SUMMARIZE_PROMPT`). Use `_build_summarize_prompt()` from `sdk/context/_strategy.py` (also needs to be made public — rename to `build_summarize_prompt`).
  - Wrap LLM call in try/except — on failure, fall back to the conversation title + first message as a basic summary.

### Step 5: Background runner — `tools/episodic/_runner.py`

New file. Follows the `TaskRunner` pattern from `tasks/_runner.py`:

```python
class EpisodicRunner:
    def __init__(self, config: EpisodicConfig):
        self._config = config
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._loop_task = asyncio.create_task(
            self._poll_loop(), name="episodic-indexer"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task:
            self._loop_task.cancel()

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await index_new_conversations()
            except Exception:
                logger.exception("Error in episodic indexer tick")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.poll_interval,
                )
                break
            except asyncio.TimeoutError:
                pass
```

### Step 6: Search tool — `tools/episodic/episodic.py`

Add to the same file as the index model:

- **`async def search_conversations(query: str, limit: int = 5) -> dict[str, object]`**
  - Loads the index
  - Tokenizes `query` into lowercase words
  - For each record, scores against `title + " " + summary` using token overlap (count of query tokens found / total query tokens)
  - Filters out zero-score results
  - Sorts by score descending, returns top `limit`
  - Returns dict with `status`, `query`, `count`, and `results` (each result: `conversation_id`, `title`, `started_at`, `turn_count`, `summary` truncated to 500 chars, `score`)
  - Docstring serves as the LLM tool description (matching `remember`/`forget` pattern)

### Step 7: Package init — `tools/episodic/__init__.py`

Re-export `search_conversations`, `EpisodicRecord`, `EpisodicRunner`, `load_index`, `remove_from_index`.

### Step 8: App startup — `server/aiohttp_app.py`

Add startup/cleanup hooks following the task runner pattern:

```python
async def _start_episodic_runner(app: web.Application) -> None:
    config = load_config()
    if not config.episodic.enabled:
        return
    from tools.episodic import EpisodicRunner
    runner = EpisodicRunner(config.episodic)
    app["episodic_runner"] = runner
    await runner.start()

async def _stop_episodic_runner(app: web.Application) -> None:
    runner = app.get("episodic_runner")
    if runner:
        await runner.stop()
```

Add to `create_app()`:
```python
app.on_startup.append(_start_episodic_runner)
app.on_cleanup.append(_stop_episodic_runner)
```

### Step 9: Cleanup on conversation delete — `server/aiohttp_app.py`

In `delete_conversation_handler`, after deleting the conversation, also remove it from the episodic index:

```python
from tools.episodic import remove_from_index
remove_from_index(conversation_id)
```

### Step 10: Agent integration — `agents/computron/agent.py`

Add `search_conversations` to the imports and TOOLS list.

Update the SYSTEM_PROMPT memory section:

```
MEMORY — remember(key, value) / forget(key). Store user preferences proactively.
search_conversations(query) searches past conversation summaries. Use when
the user references something from a previous session or when context from
past work might be relevant.
```

### Step 11: Tests — `tests/tools/episodic/`

New test files:

- **`test_episodic.py`** — Tests for `EpisodicRecord`, `load_index`/`save_index`, `remove_from_index`, `search_conversations` (scoring, limit, empty index, no matches)
- **`test_indexer.py`** — Tests for `index_new_conversations` and `_summarize_conversation` (with mocked `list_conversations`, `list_summary_records`, `load_conversation_history`, and LLM provider). Test cases: conversation with existing summary records (no LLM call), conversation needing LLM summary, conversation below `min_turns` threshold, re-indexing when turn count changes, LLM failure fallback.
- **`__init__.py`**

## Files to create
- `tools/episodic/__init__.py`
- `tools/episodic/episodic.py`
- `tools/episodic/_indexer.py`
- `tools/episodic/_runner.py`
- `tests/tools/episodic/__init__.py`
- `tests/tools/episodic/test_episodic.py`
- `tests/tools/episodic/test_indexer.py`

## Files to modify
- `config/__init__.py` — add `EpisodicConfig`, add to `AppConfig`
- `sdk/context/_strategy.py` — make `_serialize_messages` and `_build_summarize_prompt` public
- `sdk/context/__init__.py` — export `serialize_messages`, `build_summarize_prompt`
- `server/aiohttp_app.py` — add episodic runner startup/cleanup hooks, cleanup on delete
- `agents/computron/agent.py` — register `search_conversations` tool, update system prompt

## Verification

1. **Unit tests**: `just test-file tests/tools/episodic/`
2. **Manual test**: Start the app, have a few conversations, wait for the poll interval, then in a new conversation ask the agent about something from a previous session — it should call `search_conversations` and retrieve relevant context.
3. **Index file**: After the indexer runs, check `~/.computron_9000/episodic_index.json` to verify records are being created with summaries.
4. **Delete cleanup**: Delete a conversation via the UI, verify its record is removed from the index.
5. **Lint/typecheck**: `just lint && just typecheck`
