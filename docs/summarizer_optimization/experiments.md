# Experiments

Each experiment is tested in isolation against the current baseline. One change at a time.

Historical results from synthetic-only evaluation are in [`results.md`](results.md). Starting 2026-03-20, experiments are also evaluated on real compaction records and full-fidelity conversations. See [`strategy.md`](strategy.md) for evaluation methodology.

**Evaluation commands:**
```bash
# Real compaction records (primary — compares against stored baseline):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --rerun --save

# Full-fidelity conversations (pipeline test):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_full_conv_eval.py

# Synthetic (secondary — rapid iteration):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_scenarios.py --runs 3
```

## Completed

| # | Name | Verdict | Notes |
|---|------|---------|-------|
| 1 | Remove `## User's Request` section | **Keep** | Redundant with pinned message. Freed tokens, improved fact retention. |
| 2 | Selective URL retention | **Keep** | Shorter/faster summaries. Omit intermediate navigation URLs. |
| 5 | Add `## Current State` section | **Keep** | Fixes desktop state awareness. Cell-location probe went from 0/3 to ~2/3. |
| 6 | Model size comparison | **Keep mistral:7b** | Tested 12 models. mistral:7b: 92% probes, 31s. Switched from qwen3:8b. |
| 9 | Chunked summarization | **Keep** | Split → summarize → merge for long conversations. 2x faster. |
| 10 | Remove progressive shrink | **Keep** | Dead code with chunking in place. Simplified serialization. |
| 14 | Fix num_ctx, add num_predict cap, timeout | **Keep** | Bug fix: num_ctx was 60k (model native is 32k), no generation cap, no timeout. Caused 20+ min hangs. |
| 15 | Larger summarizer model | **Keep gemma3:27b** | 47%→80% remaining work, all judge scores up ~0.9 points. |
| 17 | Aggressive tool result capping (200 chars) | **Keep** | 89% probes (was 84%). Tool results are 96% of input but assistant already distills findings. |
| 22 | Remove Remaining Work section | **Keep** | Removed `## Remaining Work` — summarizer got it wrong 47-80% of the time. Agent determines remaining work from pinned request + summary + kept messages. Strengthened `## Current State` to capture in-progress work. |
| 23 | Message group–based keep_recent | **Keep** | Replaced `keep_recent=6` (raw messages) with `keep_recent_groups=2` (assistant message groups). Prevents splitting tool calls from their results at the compaction boundary. Fixed hallucination bug (record `1577ab25`) and summary bloat on re-compaction (record `014e818a`). |
| 24 | Include tool call arguments and skip trivial results | **Keep** | Include file paths/commands/URLs from tool call args in serialization. Skip trivial results (`{'success': True}`, empty stdout). Fact retention 2.90→3.85, process suppression 2.27→2.82. Coding summaries -43% size. |
| 26 | Dynamic chunk sizing + num_ctx bump | **Keep** | Chunk threshold scales with `num_ctx` instead of hardcoded 20k. Bumped num_ctx 8192→32768. 335-message compaction: broken format → proper sections in single pass. 40s vs 7-chunk merge. |

## Removed (not needed)

| # | Name | Why removed |
|---|------|-------------|
| 3 | Reorder sections | Probes already pass for "what next" — agent finds remaining work fine. |
| 4 | Relax process suppression | Scenario 05 passes 4/4 — model already preserves failed approaches. |
| 7 | Conversation-type-aware prompts | No mixed results across scenario types. Single prompt works. |
| 8 | Structured output format | No evidence current format is a problem. High risk for no clear gain. |
| 11 | Fix "Remaining Work: None" prompt | 87% probes (was 89%). Model over-lists remaining work, triggering fail patterns. |
| 13 | Include original request as summarizer context | Was designed to help with Remaining Work accuracy. Remaining Work section removed in experiment 22, making this obsolete. |
| 19 | Tool result fact extraction | 89% probes but +5-19s latency. Stale tool data confuses summarizer on task-tracking. |
| 20 | Stronger retry suppression prompt | No change. 47%→47% remaining work, 2.27→2.33 process. Prompt too subtle for 7B model. |
| 21 | Gemma3 smaller size (12b) | 60% remaining work (vs 80% for 27b) at 19.2s (vs 25.5s). Only 6s faster but 20% worse. |

## Future experiments

### Experiment 18: Two-phase summarization (facts + state)

**What**: Split the single summarization call into two focused passes:

1. **Facts pass** — "Extract all facts, data, findings, URLs, prices, names, and results from this conversation." Higher tool result cap (e.g., 2k) so data-heavy outputs aren't lost. Output: a flat list of facts.

2. **State pass** — "Given these facts and the recent messages, produce the final summary with Current State section." Lower tool result cap (200 chars) since this pass only needs the assistant reasoning to understand workflow/progress. Output: the structured 3-section summary.

**Why it might help**: Analysis of 1,729 tool→assistant transitions shows 89% of assistant messages after tool results are empty or short transitions. Tool results carry the actual data but get capped to 200 chars. Experiment 24 improved this by including tool args, but the actual tool output content is still lost. A facts pass with a higher cap could recover this data.

**Cost**: 2 LLM calls instead of 1. With gemma3:27b at ~20-40s each, total would be ~40-80s vs ~20-40s currently.

**Risk**: Medium. Two calls means two points of failure and more latency. Need to verify the existing test suite doesn't regress.

### Experiment 25: Remove prior summary special handling

**What**: Remove `_extract_prior_summary` and the special summary skip in `_serialize_messages`. Let prior summaries serialize as normal assistant messages instead of being extracted, skipped, and re-injected as a special "EXISTING SUMMARY" preamble.

**Why**: The extract/skip/re-inject flow creates edge cases:
- When the only compactable message is a prior summary, the serialized input is empty and the LLM re-emits the summary bloated (record `014e818a`: 5.8k → 6.2k chars).
- `_extract_prior_summary` only finds the first summary; if there were multiple, others would be silently dropped.
- The "EXISTING SUMMARY ... merge ALL its facts" instruction causes the LLM to copy everything verbatim instead of compressing, leading to summary bloat over successive compactions (3.3k → 5.7k → 7.2k observed in the interactive_ml conversation chain).

**Proposed change**: Delete `_extract_prior_summary`. Remove the `startswith(_SUMMARY_PREFIX): continue` skip in `_serialize_messages`. Remove the `prior_summary` parameter from `_summarize` and `_call_summarizer`. Keep the prompt instruction about preserving facts from earlier summaries but make it general rather than tied to extraction.

**Risk**: Low-medium. The LLM might compress prior summary facts more aggressively without the explicit "merge ALL" instruction. Test with `run_real_eval.py --rerun` on records that have prior summaries.
