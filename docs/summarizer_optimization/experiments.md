# Experiments

Each experiment is tested in isolation against the current baseline. One change at a time. Results recorded in [`results.md`](results.md).

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

## Removed (not needed)

| # | Name | Why removed |
|---|------|-------------|
| 3 | Reorder sections | Probes already pass for "what next" — agent finds remaining work fine. |
| 4 | Relax process suppression | Scenario 05 passes 4/4 — model already preserves failed approaches. |
| 7 | Conversation-type-aware prompts | No mixed results across scenario types. Single prompt works. |
| 8 | Structured output format | No evidence current format is a problem. High risk for no clear gain. |

## Future experiments

### Experiment 11: Fix "Remaining Work: None" on incomplete tasks

**What**: Add explicit rules to the prompt to prevent the summarizer from marking remaining work as "None" when the task isn't actually complete. The current prompt says to write "None" if the task is complete, but the model sometimes marks tasks as done when they're not — especially after merges where the prior summary's remaining work gets lost.

**Discovered via**: Scenario 01 (merge compaction). The user asked to compare headphones and check comfort reviews. Sony and Sennheiser comfort was checked, but Bose was not. After the merge, the summary says "Remaining Work: None" — the agent would stop working prematurely.

**Proposed change**: Add a rule: "For Remaining Work, carefully check whether ALL aspects of the user's request have been addressed. If any topic was mentioned but not fully investigated, or any comparison is incomplete, list it. Only write 'None' if every part of the request is definitively complete."

**Risk**: Low. Might cause the model to over-list remaining work (listing things that are actually done). Better to err on the side of listing too much than missing work.

### Experiment 13: Include original request as summarizer context

**What**: Pass the pinned first user message to the summarizer as reference context, so it can compare what was requested vs what was done when filling the Remaining Work section.

**Discovered via**: Experiment 11 failed because the summarizer couldn't determine remaining work — it never sees the original request (it's pinned and excluded from compactable messages by design).

**Proposed change**: In `_summarize`, extract the first user message and prepend it to the serialized conversation as reference context: "ORIGINAL REQUEST (for reference — do not summarize, use to determine remaining work): [message]"

**Risk**: Very low. Adds ~50 tokens. The model might echo the request in the summary, but the "Do NOT echo" rule should handle that.

**Status**: Previously discarded (experiment ran 2026-03-17, 4% regression). But the test suite at the time had no false completion scenario. Re-test on real compaction 9 data (2026-03-18) showed it drops mistral:7b false completions from 100% to 40%. Should re-run with scenario 12 included in the suite.

### Experiment 15: Larger summarizer model to fix false completion

**What**: Switch from mistral:7b to a larger model (glm-4.7-flash:Q8_0, ~30B params) for summarization. The 7B model lacks the reasoning to notice when a multi-step task is partially complete — it consistently writes "Remaining Work: None" even when only 4 of 6 tests have been completed.

**Discovered via**: Production compaction 9 — 208 messages from browser test suite. Tests 1-4 completed, Tests 5-6 pending. Dashboard listing all 6 tests was present in the input, but mistral:7b ignored it. 100% false completion rate (5/5 runs say "None"). The dashboard was mentioned only once vs 16-39 mentions of the completed tests — the 7B model can't pick the signal out of the noise.

**Initial results** (compaction 9 real data, 5 runs each):

| Model | False completions | Avg time | Notes |
|-------|-------------------|----------|-------|
| mistral:7b (baseline) | 5/5 (100%) | 36s | Always says "None" |
| mistral:7b + request | 2/5 (40%) | 35s | Helps, but vague requests don't add signal |
| glm-4.7-flash:Q8_0 | 0/5 (0%) | 85s | Zero false completions, 2/5 explicitly mention Tests 5-6 |
| glm-4.7-flash:Q8_0 + request | 0/5 (0%) | 86s | Also zero, but request context didn't improve GOOD rate |

**Remaining work to do**:
- Run full scenario suite with glm-4.7-flash:Q8_0 to check for regressions
- Measure quality vs speed tradeoff (85s avg vs 3s for mistral:7b)
- Test whether a smaller-but-better model (qwen3.5:4b, qwen3:8b) can also fix this
- Consider using the larger model only for the merge pass (not per-chunk), which would be ~1 call at 10-15s

**Risk**: Medium. 85s is within the 2-minute budget but 30x slower than mistral:7b. If the chunked path makes 12 calls at 85s each, that's 17 minutes — need to verify this is per-full-compaction, not per-chunk.

### Experiment 17: Aggressive tool result capping (200 chars)

**What**: Drop `_TOOL_RESULT_CAP` from 10,000 to 200 chars. The insight: assistant messages already contain the distilled findings from tool results. In production compaction 9, tool results were 96% of input (103k chars) while assistant reasoning was only 4% (4k chars). The summarizer is drowning in DOM trees and bash output when the assistant already wrote "Task 3 complete, score 5/6."

**Discovered via**: Analysis of compaction 9 content ratio. Also inspired by ACON paper's separation of observation compression vs history compression — the assistant reasoning IS the compressed observation.

**Proposed change**:
- `_TOOL_RESULT_CAP = 200` (down from 10,000)
- Simple head truncation instead of head+tail (tail is rarely useful at 200 chars)

**Risk**: Low-medium. Tool results that contain data not echoed by the assistant (e.g., raw API responses, file contents the assistant didn't fully describe) would be lost. But the assistant typically summarizes what it found.
