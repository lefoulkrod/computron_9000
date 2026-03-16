# Summarizer Optimization Strategy

## 1. Goal

**Task continuity**: after compaction, can the agent pick up where it left off and continue working as if nothing happened?

Concretely, a good summary enables the agent to:
- Continue the current task without re-asking the user or re-doing work
- Reference specific results from earlier steps (URLs, prices, file paths, error messages)
- Understand what has been tried and what remains
- Make correct decisions that depend on earlier context (e.g., "the user rejected option A, so try B")

## 2. Scope

This optimization targets **sub-agent turns**, not the main conversation. Sub-agents are spawned for specific tasks and run autonomously with their own context windows. When their context fills up, the summarizer compacts old messages so the agent can keep working. Any agent — current or future — that gets a `ContextManager` with `SummarizeStrategy()` will hit this code.

The summarizer needs to work well across a wide variety of conversation types: web browsing, coding, GUI automation, data analysis, and whatever else agents end up doing. Test scenarios should cover this variety rather than targeting specific agent implementations.

## 3. Current Algorithm (Baseline)

**File**: `sdk/context/_strategy.py`

### Trigger

- Activates when context fill ratio >= 75% (`threshold=0.75`)
- Keeps the most recent 6 non-system messages verbatim (`keep_recent=6`)
- Pins the first user message (original request) — never summarized

### Prompt (`_SUMMARIZE_PROMPT`)

System prompt instructs the model to produce a structured 4-section document:
- `## User's Request` — original ask in 1-2 sentences
- `## Completed Work` — bullet points of results/findings (not process)
- `## Key Data` — all reference data: URLs, prices, ratings, dates, addresses, file paths, etc.
- `## Remaining Work` — what's left, or "None"

Key prompt rules:
- Structure enforcement: "MUST start with `## User's Request`"
- Wrong/right examples contrasting process narration vs fact extraction
- "MUST INCLUDE every URL visited or discovered"
- "MUST INCLUDE all prices, ratings, quantities, dates, and numerical data"
- Merge rule: "every URL, price, name, date, and detail from the prior summary MUST appear in your output"

### Serialization pipeline (`_serialize_messages`)

Three-phase pipeline:

1. **Page snapshot dedup** (`_dedup_page_snapshots`) — browser tools return full page state on every click/scroll. Only the last snapshot per base URL (ignoring query params) is kept; earlier ones are replaced with `[page snapshot — superseded by later snapshot]`. Typically cuts 70-80% of redundant content.

2. **Per-result cap** (`_TOOL_RESULT_CAP = 10,000`) — individual tool results over 10k chars are truncated with head+tail (5k each). Catches outliers like huge terminal logs.

3. **Total budget** (`_TOTAL_CHAR_BUDGET = 40,000`) — if total serialized text exceeds 40k chars (~10k tokens), tool results are progressively shrunk oldest-first through stages (2000 -> 500 -> omitted). Most recent results are preserved longest.

### Model

- **Summary model**: `qwen3:8b` (configured in `config.yaml` under `summary:`)
- **Context window**: 60,000 tokens (`num_ctx: 60000`)
- **Temperature**: 0.3, **Top-k**: 20
- **Think mode**: disabled

## 4. Test Strategy

### Method

**Scientific approach — one change at a time.** For each proposed change:
1. Run all synthetic scenarios against the current baseline
2. Apply exactly one change
3. Re-run all scenarios
4. Record results: fact retention, structure compliance, summary length, time
5. Compare against baseline to measure impact
6. Keep or discard the change based on results
7. If kept, it becomes the new baseline for the next change

Changes to test are prioritized in [`experiments.md`](experiments.md).

### Scoring

Primary metric: **continuity** — can the agent continue the task after compaction?

Each scenario defines **continuity probes** — questions posed to a capable agent model after summarization. The agent sees the same context it would in production: system prompt + pinned first user message + summary + last 6 kept messages. Then it answers questions like "What should you do next?" or "What was the price of X?" Probes have:
- **Pass patterns**: regex that MUST match in the response (agent knows what to do)
- **Fail patterns**: regex that must NOT match (agent is trying to redo work or lost context)

The summarizer uses the local model being tested (e.g., `qwen3:8b`). The probe uses a capable cloud model (e.g., `kimi-k2.5:cloud`) to minimize probe-side noise — we're testing the summary quality, not the probe model's capability.

Secondary metrics (tracked, not asserted):

| Metric | How measured |
|--------|-------------|
| **Time** | Wall clock seconds for summarization |
| **Summary length** | Character count (shorter is better, all else equal) |
| **Fact retention** | % of required facts found in summary (proxy, informational) |

Priority when evaluating changes: **continuity > time > length**.

Because model output is non-deterministic, run each scenario **3 times** per configuration and report min/median/max.

### Anti-regression

Results are recorded in [`results.md`](results.md).

A change is **kept** if:
- All continuity probes that were passing still pass
- At least one secondary metric improves (time down, length down)

A change is **discarded** if:
- Any continuity probe starts failing that was passing before

## 5. Test Scenarios

- Scenario files: [`scenarios/`](scenarios/) — each defines conversation, probes, and expected facts
- Test runner: `tests/sdk/context/test_scenarios.py` — parses the markdown, runs summarizer, runs probes
- Real conversation inventory: [`real_conversations/inventory.md`](real_conversations/inventory.md) (for validation after synthetic optimization)

