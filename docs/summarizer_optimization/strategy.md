# Summarizer Optimization Strategy

## 1. Goal

**Task continuity**: after compaction, can the agent pick up where it left off and continue working as if nothing happened?

Concretely, a good summary enables the agent to:
- Continue the current task without re-asking the user or re-doing work
- Reference specific results from earlier steps (URLs, prices, file paths, error messages)
- Understand what has been tried and what remains
- Make correct decisions that depend on earlier context (e.g., "the user rejected option A, so try B")

## 2. Scope

This optimization targets agent conversations — both main agents and sub-agents. When context fills up, the summarizer compacts old messages so the agent can keep working. Any agent with a `ContextManager` and `SummarizeStrategy()` will hit this code.

The summarizer needs to work well across a wide variety of conversation types: web browsing, coding, GUI automation, data analysis, and research. Test scenarios and real conversations should cover this variety.

## 3. Current Algorithm

**File**: `sdk/context/_strategy.py`

### Trigger

- Activates when context fill ratio >= 75% (`threshold=0.75`)
- Keeps the last 2 assistant message groups verbatim (`keep_recent_groups=2`). A group is an assistant message plus any following tool results, plus any interleaved user messages between groups. The boundary always falls right before an assistant message, so tool call/result pairs are never split.
- Pins the first user message (original request) — never summarized

### Prompt (`_SUMMARIZE_PROMPT`)

System prompt instructs the model to produce a structured 3-section document:
- `## Completed Work` — bullet points of results/findings (not process)
- `## Key Data` — all reference data: URLs, prices, ratings, dates, file paths, etc.
- `## Current State` — what is happening RIGHT NOW at the end of the conversation, what was the assistant doing, what did the user most recently ask for

Key prompt rules:
- Structure enforcement: "MUST start with `## Completed Work`"
- Wrong/right examples contrasting process narration vs fact extraction
- Selective URL retention: work-critical URLs only, omit intermediate navigation
- Merge rule: all facts from prior summaries must carry forward

### Serialization pipeline (`_serialize_messages`)

1. **Page snapshot dedup** (`_dedup_page_snapshots`) — only the last snapshot per base URL is kept; earlier ones replaced with a short note. Typically cuts 70-80% of redundant content.

2. **Per-result cap** (`_TOOL_RESULT_CAP = 200`) — tool results over 200 chars are truncated (head only). Intentionally aggressive: assistant messages already contain the distilled findings. In production, tool results are ~96% of input chars but carry little unique signal beyond what the assistant summarized.

For long conversations (serialized text > 20k chars), the input is split into ~10k char chunks, each summarized independently, then merged in a final pass.

### Model

- **Summary model**: `gemma3:27b` (configured in `config.yaml` under `summary:`)
- **Context window**: 8,192 tokens (`num_ctx: 8192`)
- **Max output**: 2,048 tokens (`num_predict: 2048`)
- **Temperature**: 0.3, **Top-k**: 20
- **Timeout**: 180 seconds per LLM call

## 4. Evaluation

### Three evaluation methods

**Synthetic scenarios** (`run_scenarios.py`): Hand-crafted conversations with continuity probes. A capable cloud model (kimi-k2.5:cloud) answers questions after seeing the summary and checks if the agent could continue. Fast (seconds per scenario), good for rapid iteration, but doesn't capture real-world failure modes well. 12 scenarios covering browser, desktop, coding, research tasks.

**Real compaction records** (`run_real_eval.py`): Tests summarizer output quality on real compaction records stored in `real_compactions/`. Each record is a `SummaryRecord` from a production compaction event — contains the input messages that were compacted and the summary that was produced. Evaluated with deterministic checks + LLM-as-judge. Tests: "given this input, does the summarizer produce a good summary?"

**Full conversation eval** (`run_full_conv_eval.py`): Tests the full compaction pipeline on complete, never-compacted conversations stored in `full_conversations/`. Simulates compaction with the current strategy (boundary logic + serialization + summarization) and evaluates the result. Tests: "if we compacted this conversation, would the agent be able to continue?" Covers conversation types the compaction records don't (e.g., long coding sessions with silent tool chains).

### Real data evaluation

Each compaction in production saves a `SummaryRecord` with the input messages, prior summary, and output summary. These records are copied to `real_compactions/` and annotated with expected behavior. Currently 31 records.

**Deterministic checks** (hard pass/fail):
- `must_contain` — regex patterns for key facts that must survive (prices, URLs, names).
- `must_not_contain` — regex patterns for hallucinated content that must not appear.
- `has_all_sections` — are all 3 required section headings present?

**LLM judge** (1-5 scored, kimi-k2.5:cloud):
- `fact_retention` — are important facts preserved?
- `current_state` — does it describe where the agent left off?
- `process_suppression` — does it avoid narrating clicks/scrolls/retries?

Judge was validated for stability (5 runs on 8 records, spread 0-1) and accuracy (calibrated against 6 records where we manually verified the correct answer). kimi-k2.5:cloud was selected over deepseek-v3.2, gemini-3-flash-preview, and glm-5 based on calibration accuracy and reliability.

### Full conversation evaluation

Full-fidelity conversations are stored in `full_conversations/` — complete message histories from real agent sessions that were never compacted. Currently 2 conversations:
- `3ad4d39b` — 160-message browser flight search (tests page snapshot dedup, fact extraction)
- `f50c3081` — 161-message coding session building a rigging system (tests tool cap impact with silent assistant chains)

The runner simulates compaction using the current `keep_recent_groups` boundary logic, runs the summarizer, and evaluates with deterministic checks + LLM judge (including a hallucination score).

### Current baseline (2026-03-21, gemma3:27b)

```
Real compaction records (31 records):
  Has all sections:       100%
  Required facts found:   98%
  Fact retention:         3.85/5
  Current state:          3.36/5
  Process suppression:    2.82/5
```

Previous baselines: mistral:7b scores ~2.8/5. gemma3:27b pre-serialization-changes: fact 3.70, state 3.77, process 2.77.

### Running evaluations

```bash
# Real compaction records — baseline (evaluate stored summaries):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py

# Real compaction records — after a change (re-run summarizer, compare):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --rerun --save

# Full conversation eval:
PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py

# Synthetic scenarios (rapid iteration):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py --runs 3
```

### Acceptance criteria

A change is **kept** if:
- Real data judge scores stay same or improve
- Full conversation facts and judge scores stay same or improve
- Synthetic probe rate stays same or improves
- No single metric drops by more than 10% or 0.5 points

## 5. Known Issues

From real conversation analysis (30 compaction records across 6 conversations):

1. **Process narration** (2.77/5) — when the agent retries the same action many times (e.g., clicking a button 10 times), the summary becomes a log of attempts rather than facts. The prompt says "omit HOW results were obtained" but the model ignores this for long retry sequences.

2. **Merge fact loss** — during merge compactions, facts from the prior summary get dropped. The flight search lost all prices ($634, $558, $714) during merge despite the prompt saying "merge ALL facts."

3. **Hallucinated data** — one record (1577ab25) had the summarizer invent a recipe from a near-empty input (orphaned tool call with no results). The 200-char tool cap + boundary splitting left the summarizer with 47 chars of input. Fixed by message group–based boundaries (experiment 23).

4. **Summary bloat on re-compaction** — record 014e818a had a prior summary as the only compactable message. The `_extract_prior_summary` flow extracted it, left the serialized input empty, and the LLM re-emitted it at 6.2k chars (larger than the 5.8k input). Related to the prior summary special handling — separate fix planned.

## 6. Historical Algorithm

For reference, the original algorithm before optimization:

- **Prompt**: 4 sections starting with `## User's Request` (removed in experiment 1)
- **Tool cap**: 10,000 chars per result with head+tail preservation (reduced to 200 in experiment 17)
- **Progressive shrink**: 40k total char budget with oldest-first shrinking (removed in experiment 10)
- **Keep recent**: 6 raw messages (changed to 2 assistant message groups in experiment 23)
- **Model**: qwen3:8b with num_ctx=60000 (changed to mistral:7b in experiment 6, then gemma3:27b in experiment 15, with num_ctx=8192 in experiment 14)
- **No timeout**: could run indefinitely (added 180s timeout in experiment 14)

See `experiments.md` and `results.md` for the full history of changes.

## 7. Test Data

- `scenarios/` — 12 synthetic scenarios (markdown format with inline conversations and probes)
- `real_compactions/` — 31 production compaction records (JSON SummaryRecords) with annotations
- `real_compactions/annotations.json` — per-record expected behavior (task_complete, must_contain patterns)
- `real_compactions/baseline_scores.json` — baseline evaluation scores for comparison
- `full_conversations/` — 2 full-fidelity conversations (never compacted) for pipeline testing
- `full_conversations/annotations.json` — per-conversation expected behavior and type
