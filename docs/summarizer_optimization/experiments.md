# Experiments

Each experiment is tested in isolation against the current baseline. One change at a time.

Historical results from synthetic-only evaluation are in [`results.md`](results.md). Starting 2026-03-20, experiments are also evaluated on 30 real compaction records using deterministic checks + LLM-as-judge. See [`strategy.md`](strategy.md) for evaluation methodology.

**Evaluation commands:**
```bash
# Real data (primary — compares against stored baseline):
PYTHONPATH=. uv run python docs/summarizer_optimization/run_real_eval.py --rerun --save

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
| 17 | Aggressive tool result capping (200 chars) | **Keep** | 89% probes (was 84%). Tool results are 96% of input but assistant already distills findings. |

## Removed (not needed)

| # | Name | Why removed |
|---|------|-------------|
| 3 | Reorder sections | Probes already pass for "what next" — agent finds remaining work fine. |
| 4 | Relax process suppression | Scenario 05 passes 4/4 — model already preserves failed approaches. |
| 7 | Conversation-type-aware prompts | No mixed results across scenario types. Single prompt works. |
| 8 | Structured output format | No evidence current format is a problem. High risk for no clear gain. |
| 11 | Fix "Remaining Work: None" prompt | 87% probes (was 89%). Model over-lists remaining work, triggering fail patterns. |
| 19 | Tool result fact extraction | 89% probes but +5-19s latency. Stale tool data confuses summarizer on task-tracking. |
| 20 | Stronger retry suppression prompt | No change. 47%→47% remaining work, 2.27→2.33 process. Prompt too subtle for 7B model. |
| 15 | Larger summarizer model | **Keep gemma3:27b** | 47%→80% remaining work, all judge scores up ~0.9 points. See below. |

## Future experiments

### Experiment 13: Include original request as summarizer context

**What**: Pass the pinned first user message to the summarizer as reference context, so it can compare what was requested vs what was done when filling the Remaining Work section.

**Discovered via**: Experiment 11 failed because the summarizer couldn't determine remaining work — it never sees the original request (it's pinned and excluded from compactable messages by design).

**Proposed change**: In `_summarize`, extract the first user message and prepend it to the serialized conversation as reference context: "ORIGINAL REQUEST (for reference — do not summarize, use to determine remaining work): [message]"

**Risk**: Very low. Adds ~50 tokens. The model might echo the request in the summary, but the "Do NOT echo" rule should handle that.

**Status**: Previously discarded on synthetics (4% regression). Re-test on real compaction data showed it drops mistral:7b false completions from 100% to 40%. Should re-evaluate with full real-data eval (`run_real_eval.py --rerun`).

### Experiment 22: Remove Remaining Work section

**What**: Remove the `## Remaining Work` section from the summary entirely. The summarizer consistently gets this wrong (47% with mistral:7b, 80% with gemma3:27b), and the information is redundant — the agent can determine what remains from the pinned original request + summary + kept-recent messages.

The `## Current State` section is strengthened to capture what was happening at the end of the conversation, including in-progress work and what the user last asked for. This gives the agent the context it needs to continue without the summarizer having to predict "what's left."

**Proposed change**: Remove `## Remaining Work` from prompt. Update Current State description to emphasize recency — "what was the assistant doing in its last message? What did the user most recently ask for?"

### ~~Experiment 21: Gemma3 smaller size (12b)~~ — tested, not adopted

gemma3:12b scored 60% remaining work (vs 80% for 27b) at 19.2s avg (vs 25.5s). Only 6s faster but 20% worse on the key metric. The 27b remains the better choice.

### Experiment 18: Two-phase summarization (facts + state)

**What**: Split the single summarization call into two focused passes:

1. **Facts pass** — "Extract all facts, data, findings, URLs, prices, names, and results from this conversation." Higher tool result cap (e.g., 2k) so data-heavy outputs aren't lost. Output: a flat list of facts.

2. **State pass** — "Given these facts and the recent messages, produce the final summary with Current State and Remaining Work sections." Lower tool result cap (200 chars) since this pass only needs the assistant reasoning to understand workflow/progress. Output: the structured 4-section summary.

The state pass receives the facts pass output as input, so it doesn't need to re-read tool results — it just needs to organize the facts and determine what's current vs completed vs remaining.

**Discovered via**: Testing experiment 17 on a real GitHub repo exploration conversation. The 200-char tool cap caused the summarizer to lose data that was only in tool results (README content with game features, 14 commit count, GitHub Pages deployment URL). The assistant said "I got the README" but didn't list the game features — those were in the truncated page snapshot. For task-tracking conversations (browser tests) this was fine because the assistant echoed scores. For research/exploration conversations, tool results carry unique data the assistant didn't repeat.

The current single-pass approach forces the model to simultaneously extract facts AND track state AND determine remaining work, all from a mix of assistant reasoning and tool noise. Splitting into two passes lets each focus on what it does best.

**Proposed changes**:
- `_serialize_messages` accepts a `tool_cap` parameter instead of using the global constant
- `_call_summarizer` replaced by `_extract_facts` (tool_cap=2000) + `_build_summary` (tool_cap=200)
- Facts pass uses a simpler prompt: just extract facts, no structure required
- State pass uses the existing structured prompt but receives pre-extracted facts instead of raw conversation
- For chunked conversations: facts pass runs per-chunk, then state pass runs once on merged facts

**Cost**: 2 LLM calls instead of 1. With mistral:7b at 2-4s each, total would be ~6-8s vs ~3-4s currently. For chunked conversations, only 1 extra call (the state pass) since fact extraction replaces the existing chunk summarization.

**Expected benefits**:
- Better fact retention on research/exploration tasks (higher tool cap in facts pass)
- Better state tracking (state pass is focused, smaller input)
- Better remaining work detection (state pass sees organized facts, not raw noise)
- Facts pass could potentially use a different model than state pass

**Risk**: Medium. Two calls means two points of failure and more latency. The facts pass might produce too much output that then overwhelms the state pass. Need to cap facts pass output (maybe 3k chars). Also need to verify the existing scenario suite doesn't regress — the current single-pass approach works well for most scenarios.

**Note**: Experiment 19 (tool result fact extraction) tested a simpler version of this idea — extracting facts from tool results only, then feeding them to the normal summarizer. It failed because stale tool data confused the summarizer on task-tracking conversations. Experiment 18 differs by splitting the summarizer itself into two passes rather than pre-processing tool results.

**Test plan**:
1. Evaluate with `run_real_eval.py --rerun` — compare against baseline
2. Run synthetic scenarios to check for regressions
3. Test on GitHub repo exploration specifically for fact retention improvement
