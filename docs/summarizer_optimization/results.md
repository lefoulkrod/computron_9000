# Results

## Baseline (2026-03-15)

**What**: Current `_SUMMARIZE_PROMPT` + dedup + per-result cap (10k) + total budget (40k). Model: `qwen3:8b`. Probe model: `kimi-k2.5:cloud`.

7 runs total. Tests run individually due to async event loop sharing.

| Scenario | Probes | Time (range) | Length (range) | Fact Retention (range) |
|----------|--------|-------------|----------------|----------------------|
| 01_merge | 3/3 (7/7 runs) | 12.8–16.7s | 2,187–2,588 | 95–100% |
| 02_desktop | 3/3 (7/7 runs) | 4.3–8.8s | 1,253–2,069 | 64% |
| 03_browser_fail | 3/3 (6/7 runs) | 4.0–5.2s | 1,227–1,690 | 43–57% |
| 04_form_fill | 3/3 (6/7 runs) | 3.1–3.8s | 1,240–1,502 | 47% |
| 05_debug_fail | 3/3 (7/7 runs) | 3.2–6.3s | 1,015–1,787 | 67–87% |

**Probes passing**: 15/15 on 5 of 7 runs. 2 flaky runs had 1 probe failure each (03 and 04).

---

## Experiment Results

### Experiment 1: Remove `## User's Request` section (2026-03-15)

**What changed**: Removed `## User's Request` heading and instructions from `_SUMMARIZE_PROMPT`. Summary now starts with `## Completed Work`. The original user message is already pinned and visible to the agent.

3 runs.

| Scenario | Probes | Time (range) | Length (range) | Fact Retention (range) |
|----------|--------|-------------|----------------|----------------------|
| 01_merge | 3/3 (3/3 runs) | 16.0–19.3s | 2,530–3,190 | 95–100% |
| 02_desktop | 3/3 (3/3 runs) | 3.2–4.7s | 779–1,075 | 100% |
| 03_browser_fail | 3/3 (3/3 runs) | 5.2–6.4s | 1,530–1,904 | 71–79% |
| 04_form_fill | 3/3 (3/3 runs) | 3.0–3.5s | 1,146–1,257 | 71–82% |
| 05_debug_fail | 3/3 (3/3 runs) | 4.2–4.5s | 1,508–1,600 | 93% |

**Probes passing**: 15/15 (all 3 runs). Baseline: 15/15 (5 of 7 runs).

**Comparison to baseline**:
- Probes: same or better (no flaky failures in 3 runs vs 2 flaky in 7 baseline runs)
- Time: similar (no meaningful change)
- Length: 02_desktop dropped significantly (779–1,075 vs 1,253–2,069) — removing the redundant section freed space
- Fact retention: improved across the board — 02_desktop jumped from 64% to 100%, 04_form_fill from 47% to 71–82%

**Verdict**: Keep

### Experiment 2: Selective URL retention (2026-03-16)

**What changed**: Changed "MUST INCLUDE every URL visited or discovered" to "MUST INCLUDE URLs needed to revisit results or continue work. Omit intermediate navigation URLs." Applied on top of Experiment 1. Added scenario 06 (heavy navigation with 13 URLs, 10 unique) to specifically test this change.

6 runs total (3 initial with 5 scenarios + 3 with 6 scenarios). Reporting the 3-run set with all 6 scenarios.

| Scenario | Probes | Time (range) | Length (range) | Fact Retention (range) |
|----------|--------|-------------|----------------|----------------------|
| 01_merge | 3/3 (3/3 runs) | 10.9–13.4s | 1,774–2,253 | 95% |
| 02_desktop | 3/3 (3/3 runs) | 3.1–3.8s | 813–1,041 | 100% |
| 03_browser_fail | 3/3 (2/3 runs) | 3.8–4.0s | 1,125–1,158 | 71–79% |
| 04_form_fill | 3/3 (3/3 runs) | 2.3–2.5s | 769–859 | 71–76% |
| 05_debug_fail | 3/3 (3/3 runs) | 4.1–4.2s | 1,401–1,515 | 93% |
| 06_heavy_nav | 3/3 (3/3 runs) | 9.3–12.8s | 2,988–4,180 | 86–90% |

**Probes passing**: 18/18 (2 of 3 runs). 1 flaky run: 03_browser_fail (same probe that's flaky at baseline).

**Comparison to Experiment 1**:
- Probes: stable
- Time: 01_merge improved (16–19s down to 10–14s)
- Length: reductions across the board, especially 04_form_fill (1,146–1,257 to 769–859)
- Fact retention: stable or improved

**Verdict**: Keep

### Experiment 5: Add `## Current State` section (2026-03-16)

**What changed**: Added a `## Current State` section to the prompt between Key Data and Remaining Work. Instructs the model to describe: which application/page is open, modified files, filled vs pending form fields, unresolved errors, cell/row references, coordinates. Skipped experiments 3 and 4 to target the known-failing desktop probe.

3 runs. 21 probes per run (added cell-location probe to scenario 02, final-fix probe to 05, user-requirements probe to 06).

| Scenario | Probes | Time (range) | Length (range) | Fact Retention (range) |
|----------|--------|-------------|----------------|----------------------|
| 01_merge | 3/3 (3/3 runs) | 6.5–16.4s | 954–2,663 | 55–95% |
| 02_desktop | 4/4 (2/3 runs) | 3.5–8.0s | 1,002–1,326 | 100% |
| 03_browser_fail | 3/3 (2/3 runs) | 4.5–4.7s | 1,371–1,375 | 71–79% |
| 04_form_fill | 3/3 (3/3 runs) | 2.7–3.1s | 1,005–1,273 | 76–82% |
| 05_debug_fail | 4/4 (3/3 runs) | 4.4–4.8s | 1,564–1,729 | 100% |
| 06_heavy_nav | 4/4 (3/3 runs) | 2.6–14.4s | 1,007–4,812 | 36–91% |

**Probes passing**: 21/21 (1 of 3 runs), 20/21 (2 of 3 runs).

**Key finding — desktop cell probe**:
- Before this experiment: 0/3 runs passed (probe model said "let me take a screenshot")
- After: 2/3 runs passed — the `## Current State` section captures cell references so the agent can act without re-reading the screen

**Other observations**:
- 05_debug_fail fact retention jumped to 100% (was 87–93%) — Current State captures fix details
- High variance in 01_merge and 06_heavy_nav length/time — model is non-deterministic about how much state to include
- 03_browser_fail still has the same flaky probe (1 failure in 3 runs, same as baseline)

**Verdict**: Keep — directly fixes the desktop continuity gap and improves coding scenario detail

### Experiment 6: Model size comparison (2026-03-16)

**What changed**: Nothing — measurement only. Tested 5 models against 6 scenarios (21 probes each). Multiple runs per model.

| Model | Size | Runs | Probe rate | Avg total time | Avg length | Notes |
|-------|------|------|-----------|----------------|------------|-------|
| **mistral:7b** | 4.1 GB | 3 | **92%** (58/63) | **31s** | 0.7–2.8k | **New production model.** Best probes AND fastest of the reliable models. |
| qwen3:8b | 5.2 GB | 3 | 89% (56/63) | 44s | 1.2–4.5k | Previous baseline. Solid but slower. |
| gemma2:2b | 1.6 GB | 3 | 87% (56/63) | 19s | 0.7–2.4k | 2x faster, 3x smaller. Worth revisiting for speed-critical use. |
| phi4-mini | 2.5 GB | 3 | 87% (55/63) | 19s | 1.0–2.6k | Same speed as gemma2 but higher variance (81–95%). |
| llama3.2:3b | 2.0 GB | 1 | 86% (18/21) | 17s | 0.7–1.7k | Fast but 2 probe timeouts on cloud model. |
| mistral:7b (detail) | — | — | — | — | Run 1: 95%, Run 2: 86%, Run 3: 95%. 05_debug perfect (12/12). |
| qwen3.5:4b | 3.4 GB | 5 | 82% (86/105) | 53s | 1.1–6.4k | 100% on desktop probes. Same model as vision (no swapping). |
| llama3.2:1b | 1.3 GB | 1 | 82% (14/17) | 8s | 0.7–2.5k | 06_nav timed out. Too small for long inputs. |
| smollm2:1.7b | 1.8 GB | 1 | — | stuck | — | Can't handle the task. |

**Decision**: Switch to `mistral:7b`. Highest probe rate (92%) and 30% faster than qwen3:8b. `gemma2:2b` kept as potential speed-focused alternative.

### Experiment 9: Chunked summarization (2026-03-17)

**What changed**: When serialized conversation exceeds 20k chars, split messages into ~10k char chunks, summarize each independently, then merge chunk summaries in a final pass. Removes dependency on progressive shrink for long conversations. Applied on top of experiments 1, 2, 5, and model switch to mistral:7b.

**Discovered via**: Scenario 07 (real game creation, 213 messages, 40k serialized). The progressive shrink truncated early game-creation context while preserving late filesystem-browsing noise. Summary listed every HTML file on the system instead of describing the game.

3 runs on synthetic scenarios.

| Scenario | Probes (3 runs) | Time (range) | Length (range) | Fact Retention (range) |
|----------|----------------|-------------|----------------|----------------------|
| 01_merge | 3/3 (3/3 runs) | 8.4–9.0s | 1,909–2,049 | 88–100% |
| 02_desktop | 4/4 (1/3), 3/4 (2/3) | 2.5–2.8s | 911–979 | 73–100% |
| 03_fail | 3/3 (3/3 runs) | 2.6–2.9s | 1,082–1,244 | 55–64% |
| 04_form | 3/3 (2/3), 2/3 (1/3) | 2.5–4.0s | 1,179–1,996 | 86–93% |
| 05_debug | 4/4 (3/3 runs) | 2.1–2.3s | 722–1,008 | 58–67% |
| 06_nav | 4/4 (2/3), 3/4 (1/3) | 3.0–3.6s | 988–1,443 | 50–61% |

**Probe rate**: 57/63 (90%) — same noise band as without chunking (92%).

**Comparison to pre-chunking mistral:7b**:
- Probes: equivalent (90% vs 92%, within non-determinism)
- Time: **faster** (~22s total vs ~31s total)
- Length: **shorter** (0.7–2.0k vs 0.7–2.8k)
- Scenario 07 (real): still fails due to filesystem dump content, but chunking is a safety net for expanded context windows

**Verdict**: Keep — faster, shorter summaries, no probe regression, and protects against large-context edge cases

### Experiment 10: Remove progressive shrink (2026-03-17)

**What changed**: Removed `_TOTAL_CHAR_BUDGET`, `_shrink_tool_results`, and Phase 2 shrink logic from `_serialize_messages`. With chunking, each chunk is ~10k chars — the 40k budget never triggers within a chunk.

3 runs (after discarding first run that hit Ollama contention — empty responses).

| Scenario | Probes (3 runs) | Time (range) | Length (range) |
|----------|----------------|-------------|----------------|
| 01_merge | 2/3, 2/3, 3/3 | 8.5–9.3s | 1,774–2,172 |
| 02_desktop | 2/3, 3/4, 4/4 | 1.7–2.6s | 589–858 |
| 03_fail | 3/3 (all) | 2.1–3.2s | 856–1,364 |
| 04_form | 3/3 (all) | 2.5–3.6s | 1,177–1,677 |
| 05_debug | 4/4 (all) | 2.0–2.8s | 724–1,170 |
| 06_nav | 3/4, 4/4, 3/4 | 4.9–6.1s | 1,715–2,522 |

**Probe rate**: 55/63 (87%) — within noise of Experiment 9 (90%). Same flaky probes.

**Confirmed**: Progressive shrink was dead code. Removing it simplifies `_serialize_messages` with zero impact on output.

**Verdict**: Keep — code cleanup, no functional change

### Experiment 11: Fix "Remaining Work: None" on incomplete tasks (2026-03-17)

**What changed**: Added explicit instructions to the Remaining Work section: "Only write 'None' if EVERY part of the user's request has been fully addressed. If any comparison is incomplete, any item was mentioned but not investigated, or any step was planned but not executed, list it here."

1 full run (11 scenarios) + 2 targeted runs on scenario 01.

| Scenario | Probes | Time | Length |
|----------|--------|------|--------|
| 01_merge | 3/3, 1/1, 1/1 (flaky) | 9.3s | 2,237 |
| All others | Same as baseline | — | — |

**Finding**: The prompt change did NOT fix the root cause. The model still writes "Remaining Work: None" for scenario 01. It genuinely believes the task is complete because the Completed Work section mentions comfort feedback for Sony and Sennheiser — the model doesn't realize Bose comfort was never checked.

The probe passed on some runs anyway because the probe model (kimi-k2.5) sometimes infers from the summary content that Bose wasn't fully investigated. This is probe non-determinism, not a fix.

**Root cause**: The summarizer doesn't track what was *requested* vs what was *done*. It sees three headphones discussed with comfort info and concludes the task is complete. This is a semantic understanding problem, not a prompt engineering problem.

**Verdict**: Discard — reverted. The prompt change had no effect on the actual failure.

### Experiment 13: Include original request as summarizer context (2026-03-17)

**What changed**: Pass the pinned first user message to the summarizer as "ORIGINAL USER REQUEST (for reference — do not summarize this, use it to determine what work remains)" so it can compare request vs completed work.

1 full run + 2 targeted runs on scenario 01.

| Scenario | Probes | Time | Length | vs baseline |
|----------|--------|------|--------|-------------|
| 01_merge | 3/3 | 8.3s | 1,767 | same |
| 08_multi_compact | 3/4 | 11.2s | 2,442 | **regression** |
| All others | similar | similar | similar | — |

**Probe rate**: 34/40 (85%) — down from 36/40 (90%) baseline. Scenario 08 regressed.

**Full run (3 runs, all 11 scenarios):**

| | Baseline | Experiment 13 |
|---|---------|--------------|
| **Total probes** | 108/118 (92%) | 106/120 (88%) |
| 01_merge | 8/9 | 8/9 (unchanged) |
| 02_desktop | 12/12 | 10/12 (regression) |
| 03_fail | 9/9 | 7/9 (regression) |
| 06_nav | 10/12 | 12/12 (improvement) |
| 08_multi | 11/12 | 10/12 (regression) |

**Finding**: The original request context didn't fix the remaining work problem (01_merge still says "None") and caused regressions on 02, 03, and 08. The model gets confused by having two contexts (original request + conversation) and produces worse summaries overall.

**Verdict**: Discarded at the time — 4% regression, no improvement on target. However, the test suite lacked a false completion scenario. With scenario 12 now added, the 92% vs 88% difference may be noise. Re-tested on real compaction 9 data (2026-03-18): passing the original request dropped mistral:7b false completions from 100% to 40% (5 runs). Worth re-evaluating with the full suite including scenario 12.

### New baseline (2026-03-18)

12 scenarios (added scenario 12: false completion). Model: mistral:7b. Config: num_ctx=8192, num_predict=2048, temperature=0.3, top_k=20. 3 runs.

| Scenario | Probes (3 runs) | Time (range) | Length (range) |
|----------|----------------|-------------|----------------|
| 01_merge | 3/3, 3/3, 3/3 | 7.7–16.1s | 1,603–2,139 |
| 02_desktop | 2/4, 4/4, 3/4 | 1.9–2.9s | 568–973 |
| 03_fail | 2/3, 3/3, 3/3 | 2.3–4.3s | 831–1,637 |
| 04_form | 3/3, 3/3, 2/3 | 2.2–3.9s | 867–1,544 |
| 05_debug | 3/4, 3/4, 3/4 | 2.1–2.6s | 644–820 |
| 06_nav | 4/4, 3/4, 4/4 | 3.5–11.0s | 1,160–3,439 |
| 07_real | 2/3, 2/3, 2/3 | 7.9–8.1s | 2,769–2,842 |
| 08_multi | 3/4, 4/4, 3/4 | 12.9–39.1s | 2,334–3,207 |
| 09_mixed | 4/4, 4/4, 4/4 | 3.3–8.7s | 1,251–1,548 |
| 10_redirect | 3/4, 3/4, 3/4 | 2.2–11.8s | 761–1,081 |
| 11_long | 4/4, 4/4, 4/4 | 2.5–7.0s | 613–2,164 |
| 12_false | 3/3, 3/3, 0/3 | 2.7–3.7s | 798–1,159 |

**Probe rate**: 109/129 (84%).

### Experiment 17: Aggressive tool result capping — 200 chars (2026-03-18)

**What changed**: Dropped `_TOOL_RESULT_CAP` from 10,000 to 200 chars. Changed truncation from head+tail to simple head truncation. Rationale: in production compaction 9, tool results were 96% of input (103k chars) while assistant reasoning was 4% (4k chars). The assistant messages already contain the distilled findings; tool outputs are mostly noise for the summarizer.

3 runs, 12 scenarios.

| Scenario | Probes (3 runs) | Time (range) | Length (range) |
|----------|----------------|-------------|----------------|
| 01_merge | 2/3, 3/3, 3/3 | 5.3–5.9s | 1,116–1,472 |
| 02_desktop | 4/4, 4/4, 4/4 | 2.5–3.1s | 825–1,190 |
| 03_fail | 3/3, 1/3, 1/3 | 1.2–1.7s | 453–577 |
| 04_form | 3/3, 3/3, 3/3 | 2.3–3.0s | 953–1,202 |
| 05_debug | 4/4, 4/4, 4/4 | 2.1–2.9s | 822–1,234 |
| 06_nav | 4/4, 4/4, 3/4 | 5.7–6.2s | 1,970–2,299 |
| 07_real | 1/3, 3/3, 2/3 | 1.7–2.1s | 657–904 |
| 08_multi | 4/4, 4/4, 3/4 | 6.6–8.4s | 1,024–1,450 |
| 09_mixed | 4/4, 4/4, 4/4 | 1.8–2.2s | 719–874 |
| 10_redirect | 3/4, 2/4, 3/4 | 2.2–3.9s | 777–1,482 |
| 11_long | 4/4, 4/4, 4/4 | 6.3–7.8s | 2,193–2,670 |
| 12_false | 3/3, 3/3, 3/3 | 3.6–3.9s | 1,072–1,226 |

**Probe rate**: 115/129 (89%) — up from 109/129 (84%) baseline.

**Key improvements**:
- 02_desktop: 12/12 (was 9/12) — perfect
- 05_debug: 12/12 (was 9/12) — perfect
- 08_multi: 11/12 (was 10/12)
- 12_false: 9/9 (was 8/9) — perfect

**Key regressions**:
- 03_fail: 5/9 (was 8/9) — notable regression, needs investigation

**Also tested on real compaction 9 data** (208 messages, false completion case): 0/5 false completions with 200 char cap (was 5/5 with 10k cap). Average time: 4.5s (was 36s).

**Verdict**: Keep — 5% probe improvement, 12× faster on real data, eliminates false completion on real conversation. The 03_fail regression needs monitoring but is offset by improvements elsewhere.

### Experiment 19: Tool result fact extraction before summarization (2026-03-19)

**What changed**: Added a pre-processing step at compaction time that batches tool results and runs an LLM call to extract key facts before the summarizer sees them. Tool results are replaced with extracted bullet points instead of being truncated at 200 chars. Extraction cap: 4000 chars per tool result. Extra LLM call per compaction.

3 runs, 12 scenarios.

| Scenario | Probes (3 runs) | Time (range) | Length (range) |
|----------|----------------|-------------|----------------|
| 01_merge | 2/3, 3/3, 2/3 | 4.6–6.4s | 843–1,507 |
| 02_desktop | 4/4, 3/4, 4/4 | 1.7–2.9s | 562–1,086 |
| 03_fail | 1/3, 3/3, 2/3 | 1.4–2.7s | 458–516 |
| 04_form | 3/3, 3/3, 3/3 | 2.8–3.5s | 952–1,210 |
| 05_debug | 4/4, 4/4, 4/4 | 2.0–12.5s | 773–884 |
| 06_nav | 4/4, 4/4, 4/4 | 5.6–6.7s | 2,046–2,543 |
| 08_multi | 4/4, 4/4, 4/4 | 6.5–8.8s | 1,108–1,592 |
| 09_mixed | 4/4, 4/4, 4/4 | 1.9–2.0s | 708–809 |
| 10_redirect | 3/4, 2/4, 3/4 | 1.8–2.8s | 640–1,096 |
| 11_long | 4/4, 4/4, 4/4 | 5.6–11.0s | 1,958–2,239 |
| 12_false | 2/3, 2/3, 1/3 | 2.5–14.6s | 820–1,116 |
| 13_stale | 4/4, 3/4, 4/4 | 3.0–4.3s | 655–955 |

**Probe rate**: 117/132 (89%) — same as experiment 17 baseline.

**Also tested on real conversations**:

| Conversation | Without extraction | With extraction | Delta |
|---|---|---|---|
| Browser tests (194 msgs) | 1,875 chars, good detail | 1,236 chars, **stale data leaked in** | +8s, worse |
| Browser tests merge (169 msgs) | 2,480 chars, clean | 7,176 chars, **bloated with process noise** | +19s, worse |
| GitHub repo (34 msgs) | 1,264 chars, missing game features | 1,377 chars, **game description recovered** | +5s, better |
| Sprite creation (25 msgs) | 1,120 chars | 943 chars | +7s, neutral |

**Finding**: Extraction helps on research/exploration tasks (GitHub repo — game description recovered) but hurts on task-tracking conversations (browser tests — stale page data and process noise leak in). Page snapshots contain both useful data AND stale state, and the extraction model can't distinguish them. The assistant reasoning is a better signal for task-tracking, while tool results are better for data-gathering. One-size-fits-all extraction doesn't work.

**Verdict**: Discard — no probe improvement over experiment 17, adds 5-19s latency, degrades quality on task-tracking conversations.

### Experiment 11: Fix "Remaining Work: None" prompt (2026-03-19)

**What changed**: Added explicit instructions to the Remaining Work section: "Only write 'None' if EVERY part of the task has been fully addressed. If the conversation mentions steps that were planned but not yet executed, items that were listed but not all completed, or a checklist where some items remain, list them here."

3 runs, 12 scenarios.

**Probe rate**: 115/132 (87%) — down from 115/129 (89%) baseline.

**Scenario 12 (false completion)**: 9/9 — still perfect, prompt didn't hurt.

**Regressions**: Scenario 03 (3/9 vs 5/9), scenario 11 (10/12 vs 12/12). The model over-lists remaining work on scenarios where the task was actually complete, triggering fail patterns.

**Real data** (compaction 9, 3 runs): 2/3 OK, 1/3 BAD (says "None"). No improvement over baseline which was also 0/5 BAD.

**Verdict**: Discard — 2% regression, model over-lists remaining work. The prompt tweak causes the opposite problem: instead of missing remaining work, it invents remaining work on completed tasks.

### Experiment 15: Larger summarizer model (2026-03-20)

**What changed**: Tested 7 model families as summarizer replacements for mistral:7b. Evaluated on 30 real compaction records using deterministic checks + LLM-as-judge (kimi-k2.5:cloud).

**Key finding**: Model size and architecture matter far more than prompt engineering. Experiments 11 and 20 (prompt tweaks) moved remaining work by 0-3%. Switching models moved it by 3-43%.

| Model | Size | Remain Work | Fact | Remain (judge) | State | Process | Avg Time |
|-------|------|-------------|------|----------------|-------|---------|----------|
| mistral:7b (baseline) | 4.4 GB | 47% | 2.90 | 2.80 | 2.83 | 2.27 | 6.0s |
| qwen3.5:4b | 3.4 GB | 60% | 2.80 | 2.80 | 2.63 | 2.40 | 9.8s |
| qwen3.5:cloud | cloud | 60% | 2.80 | 2.50 | 2.77 | 2.27 | 9.3s |
| glm-4.7-flash:Q8_0 | 31 GB | 53% | 2.90 | 2.80 | 2.97 | 2.57 | 8.0s |
| kimi-k2.5:cloud | cloud | 50% | 2.73 | 2.63 | 2.87 | 2.40 | 8.5s |
| glm-5:cloud | cloud | 70% | 4.10 | 4.47 | 4.27 | 3.40 | 12.7s |
| **gemma3:27b** | **17 GB** | **80%** | **3.70** | **3.67** | **3.77** | **2.77** | **25.5s** |
| gemini-3-flash:cloud | cloud | 90% | 4.17 | 4.60 | 4.37 | 3.33 | 12.4s |

**Observations**:
- qwen3.5 family plateaus at 60% regardless of size (4b and cloud both hit 60%)
- glm-4.7-flash (30B local) barely improves over mistral:7b despite being 7x larger
- Google's model family (gemma3/gemini) dominates — gemma3:27b at 80%, gemini-flash at 90%
- kimi-k2.5:cloud is a poor summarizer despite being a good judge
- Cloud models aren't consistently better than local — kimi (50%) and qwen3.5:cloud (60%) scored below gemma3:27b local (80%)

**Also tested (too slow — timed out or >2min per record)**:
- nemotron-3-super:cloud — timed out on record 4
- deepseek-v3.2:cloud — extremely slow (was 1089s for 30 judge calls)
- minimax-m2.7:cloud — timed out within 2 minutes on first record

**Also tested (smaller variant)**:
- gemma3:12b (8.1 GB) — 60% remaining work, 19.2s avg. Only 6s faster than 27b but 20% worse on remaining work. Not worth the tradeoff.

**Decision**: Adopt gemma3:27b. It fits on a single RTX 3090 (17 GB), gets 80% remaining work (up from 47%), and all judge scores improve by ~0.8-0.9 points. Speed is 25.5s avg (4x slower than mistral:7b) but within the 180s timeout budget.

**Verdict**: Keep — gemma3:27b replaces mistral:7b as the summarizer model.

### Experiment 20: Stronger retry suppression prompt (2026-03-20)

**What changed**: Added specific prompt rule: "If the assistant repeated or retried an action multiple times, report ONLY the final outcome."

**Real data**: 47% → 47% remaining work, 2.27 → 2.33 process suppression. Within noise.

**Verdict**: Discard — prompt engineering too subtle for 7B model. (Tested before model switch to gemma3:27b.)
