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
- Keeps the most recent 6 non-system messages verbatim (`keep_recent=6`)
- Pins the first user message (original request) — never summarized

### Prompt (`_SUMMARIZE_PROMPT`)

System prompt instructs the model to produce a structured 4-section document:
- `## Completed Work` — bullet points of results/findings (not process)
- `## Key Data` — all reference data: URLs, prices, ratings, dates, file paths, etc.
- `## Current State` — what application/page is open, modified files, form state
- `## Remaining Work` — what's left, or "None"

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

### Two evaluation methods

**Synthetic scenarios** (`run_scenarios.py`): Hand-crafted conversations with continuity probes. A capable cloud model (kimi-k2.5:cloud) answers questions after seeing the summary and checks if the agent could continue. Fast (seconds per scenario), good for rapid iteration, but doesn't capture real-world failure modes well. 12 scenarios covering browser, desktop, coding, research tasks.

**Real compaction records** (`run_real_eval.py`): Summaries from actual agent conversations stored in `real_compactions/`. Evaluated with deterministic checks + LLM-as-judge (kimi-k2.5:cloud). Slower (minutes for 30 records), but tests against real failure modes. This is the ground truth.

### Real data evaluation

Each compaction in production saves a `SummaryRecord` with the input messages, prior summary, and output summary. These records are copied to `real_compactions/` and annotated with expected behavior.

**Deterministic checks** (hard pass/fail):
- `remaining_work_correct` — does the summary correctly say "None" or not? We know for each record whether the task was actually complete.
- `must_contain` — regex patterns for key facts that must survive (prices, URLs, names).
- `has_all_sections` — are all 4 required section headings present?

**LLM judge** (1-5 scored, kimi-k2.5:cloud):
- `fact_retention` — are important facts preserved?
- `remaining_work` — is the remaining work section accurate?
- `current_state` — does it describe where the agent left off?
- `process_suppression` — does it avoid narrating clicks/scrolls/retries?

Judge was validated for stability (5 runs on 8 records, spread 0-1) and accuracy (calibrated against 6 records where we manually verified the correct answer). kimi-k2.5:cloud was selected over deepseek-v3.2, gemini-3-flash-preview, and glm-5 based on calibration accuracy and reliability.

### Current baseline (2026-03-20, gemma3:27b)

```
Deterministic:
  Remaining work correct: 80%
  Has all sections:       100%
  Required facts found:   97%

LLM judge (30 records):
  Fact retention:         3.70/5
  Remaining work:         3.67/5
  Current state:          3.77/5
  Process suppression:    2.77/5
```

Previous baseline (mistral:7b): remaining work 47%, judge scores ~2.8/5.
Synthetic probe rate: 88% (12 scenarios × 3 runs, with mistral:7b — not yet re-run with gemma3:27b).

### Running evaluations

```bash
# Baseline (evaluate stored production summaries):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py

# After a change (re-run summarizer, compare to baseline):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --rerun --save

# Synthetic scenarios (rapid iteration):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py --runs 3
```

### Acceptance criteria

A change is **kept** if:
- Real data remaining work % stays same or improves
- Real data judge scores stay same or improve
- Synthetic probe rate stays same or improves
- No single metric drops by more than 10% or 0.5 points

## 5. Known Issues

From real conversation analysis (30 compaction records across 6 conversations):

1. **False "Remaining Work: None"** (47% error rate) — the summarizer says the task is complete when it isn't. Worst on sub-agents that don't know they're part of a larger task, and on multi-step tasks where completed steps dominate the conversation.

2. **Process narration** (2.27/5) — when the agent retries the same action many times (e.g., clicking a button 10 times), the summary becomes a log of attempts rather than facts. The prompt says "omit HOW results were obtained" but the model ignores this for long retry sequences.

3. **Merge fact loss** — during merge compactions, facts from the prior summary get dropped. The flight search lost all prices ($634, $558, $714) during merge despite the prompt saying "merge ALL facts."

4. **Hallucinated data** — one record (8f1a0966) had the summarizer invent SSD prices that didn't exist in the input. The 200-char tool cap means the model sometimes fills in plausible-sounding data instead of admitting the information was truncated.

## 6. Historical Algorithm

For reference, the original algorithm before optimization:

- **Prompt**: 4 sections starting with `## User's Request` (removed in experiment 1)
- **Tool cap**: 10,000 chars per result with head+tail preservation (reduced to 200 in experiment 17)
- **Progressive shrink**: 40k total char budget with oldest-first shrinking (removed in experiment 10)
- **Model**: qwen3:8b with num_ctx=60000 (changed to mistral:7b with num_ctx=8192 in experiments 6/14)
- **No timeout**: could run indefinitely (added 120s timeout in experiment 14)

See `experiments.md` and `results.md` for the full history of changes.

## 7. Test Data

- `scenarios/` — 12 synthetic scenarios (markdown format with inline conversations and probes)
- `real_compactions/` — 30 production compaction records (JSON SummaryRecords) with annotations
- `real_compactions/annotations.json` — per-record expected behavior (task_complete, must_contain patterns)
- `real_compactions/baseline_scores.json` — baseline evaluation scores for comparison
