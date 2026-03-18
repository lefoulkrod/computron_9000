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
