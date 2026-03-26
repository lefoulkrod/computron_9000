# Summarizer Optimization Changelog

A record of how the Computron 9000 context compaction system evolved through systematic experimentation.

## 2026-03-25 — Thinking excerpts in serialization (Experiment 27)

**Change**: When an assistant message has no visible content (just tool calls), include a truncated excerpt of the `thinking` field (up to 200 chars) in the serialized summarizer input. This gives the summarizer context about *why* a tool was called.

**Why**: Multi-agent conversations produce sub-agent compactions where coding agents read large files with empty assistant content — all analysis lives in the `thinking` field. Without it, the summarizer sees bare `[Called: read_file(path)]` entries and extracts noise from truncated file contents. The PAUSE_BUTTON_FIXER sub-agent produced a summary mentioning "charset meta tag" and "ctx.drawImage" instead of the actual task (fixing a pause button on iOS PWA). With thinking excerpts, the summary correctly captures the task objective and what the agent was looking for.

**Results**:
- PAUSE_BUTTON_FIXER: useless summary → functional (task objective preserved)
- 10 recent production compactions: no regressions, sub-agent summaries 30-70% more informative
- Real eval (34 records): fact 3.79 (+0.03), state 3.42 (+0.24), process 2.88 (+0.06)
- Full conversations (2): fact 4.00, state 4.00, process 3.00, hallucination 5.00

---

## 2026-03-22 — Dynamic chunk sizing (Experiment 26)

**Change**: Chunk threshold now scales with the summarizer's `num_ctx` config instead of being hardcoded at 20k chars. With `num_ctx: 32768`, the threshold is ~78k chars, allowing large compactions to run as a single pass instead of being split into 7+ chunks and merged.

**Why**: A 335-message compaction (63k serialized chars) was split into 7 chunks. The merge pass lost format discipline — the summary broke section structure, lost prior summary facts, and roleplayed as a chatbot ("I'm here to help!"). Single-pass with a larger context window produced proper format, preserved all facts, and completed in 40s.

**Config change**: `num_ctx: 8192` → `num_ctx: 32768`

**Results**:
- 335-message compaction: broken format → proper sections, facts preserved, no roleplay
- No regression on smaller inputs
- Real eval (33 records): fact 3.76, state 3.18, process 2.82

---

## 2026-03-21 — Tool arg serialization + trivial skip (Experiment 24)

**Change**: Two improvements to `_serialize_messages`:
1. Include key tool call arguments (file paths, commands, URLs) in serialized output
2. Skip trivial tool results (`{'success': True}`, empty stdout) that carry no information

**Why**: Analysis of 1,729 tool→assistant transitions showed 89% of assistant messages after tool results are empty (47%) or short transitions (42%). The actual data was only in tool results, which got capped to 200 chars. Including tool args gives the summarizer "what was done" even when both assistant and tool result are empty.

**Results**:
- Real eval: fact 2.90→3.85 (+0.95), state 2.83→3.36 (+0.53), process 2.27→2.82 (+0.55)
- Coding summary: 6,510→3,695 chars (-43%), dramatic process noise reduction
- Browser summary: 2,776→2,053 chars (-26%), all facts preserved

---

## 2026-03-21 — Message group boundaries (Experiment 23)

**Change**: Replaced `keep_recent=6` (raw message count) with `keep_recent_groups=2` (assistant message groups). The compaction boundary now always falls before an assistant message, preventing tool calls from being split from their results.

**Why**: `keep_recent=6` could split an assistant tool call from its tool result. Record `1577ab25`: the compactable window contained only an orphaned tool call (47 chars serialized). gemma3:27b hallucinated an entire recipe from thin air. Record `014e818a`: the only compactable message was a prior summary, which got re-summarized into a bloated 6.2k chars (larger than the 5.8k input).

**Results**:
- Eliminates the hallucination class of bugs
- Eliminates the re-compaction bloat class of bugs

---

## 2026-03-20 — Remove Remaining Work section (Experiment 22)

**Change**: Removed `## Remaining Work` from the summary format, leaving 3 sections: Completed Work, Key Data, Current State. Strengthened Current State to capture in-progress work.

**Why**: The summarizer got Remaining Work wrong 47% of the time with mistral:7b and 20% with gemma3:27b. It would say "None" when work remained, or list items that were already done. The agent can determine what remains from the pinned original request + summary + kept-recent messages.

---

## 2026-03-20 — Switch to gemma3:27b (Experiment 15)

**Change**: Switched summarizer model from mistral:7b to gemma3:27b. Added model unloading after compaction to free VRAM.

**Why**: Systematic comparison of 10+ models. gemma3:27b scored 80% remaining work accuracy (vs 47% for mistral:7b), all judge scores up ~0.9 points. Google model family (gemma/gemini) consistently outperformed others.

**Config**: gemma3:27b, num_ctx: 8192, num_predict: 2048, temperature: 0.3, top_k: 20

---

## 2026-03-20 — Aggressive tool result capping (Experiment 17)

**Change**: Reduced `_TOOL_RESULT_CAP` from 10,000 to 200 chars. Tool results are truncated to 200 chars in the serialized summarizer input.

**Why**: Tool results (page snapshots, bash output) were 96% of input chars but the assistant messages already contained distilled findings. Capping to 200 chars improved probe scores from 84% to 89% by reducing noise.

---

## 2026-03-19 — Fix compaction hang (Experiment 14)

**Change**: Fixed `num_ctx` from 60,000 to 8,192. Added `num_predict: 2048` generation cap. Added 180-second timeout.

**Why**: `num_ctx: 60000` exceeded mistral:7b's native 32k context, causing model reloads and RoPE-extended inference. No `num_predict` meant runaway generation. A conversation was stuck "summarizing for 20 minutes."

---

## 2026-03-19 — Chunked summarization (Experiment 9)

**Change**: For conversations over 20k serialized chars, split into ~10k chunks, summarize each independently, then merge in a final pass.

**Why**: Large conversations exceeded the summarizer's context window. Chunking made it 2x faster and enabled handling arbitrarily long conversations.

---

## 2026-03-19 — Current State section (Experiment 5)

**Change**: Added `## Current State` section to capture what page/application is open, what the assistant was doing, in-progress work.

**Why**: Desktop agent tasks lost track of which application was open after compaction. Adding Current State fixed desktop state awareness (cell-location probe went from 0/3 to ~2/3).

---

## 2026-03-19 — Initial optimization round (Experiments 1-2)

**Changes**:
- Removed `## User's Request` section (redundant with pinned first user message)
- Added selective URL retention (keep work-critical URLs, omit intermediate navigation)

**Starting point**: qwen3:8b with num_ctx=60000, 10k tool cap, progressive shrink, 4-section prompt.

---

## Evaluation methodology

All experiments evaluated against:
- **33 real compaction records** from production conversations with deterministic fact checks + LLM-as-judge (kimi-k2.5:cloud)
- **2 full-fidelity conversations** (browser flight search, coding rigging system) testing the complete pipeline
- **12 synthetic scenarios** with continuity probes
- **50 unit tests** for boundary logic and serialization

See [`strategy.md`](strategy.md) for detailed methodology and [`experiments.md`](experiments.md) for individual experiment details.
