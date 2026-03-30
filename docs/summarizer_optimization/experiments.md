# Summarizer Optimization Experiments

## Setup

Real `SummaryRecord` data lives in `~/.computron_9000/conversations/*/summaries/*.json`.
Each record contains `input_messages` (the messages that were compacted) and `summary_text`
(what the model produced). The runner at `run_prompt_eval.py` replays records through
different configs and prints side-by-side comparisons.

```bash
# Run all experiments against all available records:
PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py

# Filter to a specific record:
PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py --record fc31d282

# Skip a config variant:
PYTHONPATH=. uv run python docs/summarizer_optimization/run_prompt_eval.py --skip-baseline
```

---

## Experiment 1 — Model swap: gemma3:27b → kimi-k2.5:cloud (2026-03-29)

**Hypothesis:** kimi-k2.5:cloud produces better summaries than gemma3:27b on both
browser research and code analysis tasks.

**Config change:** `config.yaml` summary model + num_predict bump.

**Findings:**

| Task | gemma3:27b | kimi-k2.5:cloud |
|------|-----------|-----------------|
| Browser research (68 msgs) | Vague ("Spine docs accessed"), URL lists only | Specific technical content, tier differences, architecture details |
| Code analysis (61 msgs) | Good structured output | **Failed at ≤4096 tokens** — regurgitated input verbatim |
| Code analysis (61 msgs, 8192 tokens) | — | Excellent: signatures, patterns, architecture, 20.5s |

**Root cause of kimi failure:** `num_predict: 2048` caused mid-generation truncation;
the cloud model then regurgitated its input. Fixed by setting `num_predict: 8192`.

**Result:** Switched to `kimi-k2.5:cloud` with `num_predict: 8192`. ✅

---

## Experiment 2 — Prompt + per-tool truncation (2026-03-29)

**Hypothesis:** Two changes together improve summary quality, especially for code tasks:

1. **Updated prompt** — adds code-specific guidance (preserve signatures/definitions,
   not just file paths), code WRONG/RIGHT example alongside the browser one, and
   explicit mention of code key data types (signatures, API contracts, test results).

2. **Per-tool result caps** — code tools (`read_file`, `grep`, `run_bash_cmd`) capped
   at 1500 chars instead of 200. Browser tools bumped from 200 to 400-800 chars.
   Rationale: for code tasks, assistant messages are typically `content=0` so the tool
   result is the only signal. For browser tasks, 200 chars cuts off structured data
   (prices, ratings) mid-sentence even after page dedup.

**Baseline caps (before):**
- All tools: 200 chars

**New caps (final):**
| Tool | Old | New | Reason |
|------|-----|-----|--------|
| `read_file` | 200 | 1500 | Captures docstring + first class def; higher caps break kimi (see Exp 3) |
| `grep` | 200 | 1500 | Match content IS the data |
| `run_bash_cmd` | 200 | 1500 | Output IS the data |
| `list_dir` | 200 | 800 | Directory structure needed |
| `open_url` | 200 | 500 | Capture structured data, not just page title |
| `read_page` | 200 | 800 | More structured, worth more context |
| `browse_page` | 200 | 500 | Moderate |
| `scroll_page` | 200 | 400 | Slight bump |
| `apply_text_patch` | 200 | 400 | Show result |
| `replace_in_file` | 200 | 400 | Show result |

**File read dedup analysis (2026-03-29):** Checked all 6 real SummaryRecords for repeated
reads of the same file within a single compaction window. Result: 0 savings across all records —
no file was read more than once per window. Dedup provides no measurable benefit on current data.

---

## Experiment 3 — Higher file read caps (FAILED, 2026-03-29)

**Hypothesis:** Increasing `read_file` cap to 40k (or even 6k) would improve code summaries
since real files are 6k-36k chars and 1500 only captures the first ~4% of content.

**Cap candidates tested (on record `203cf4d9`, TEST_RIG_CREATOR, 14 msgs, 6 reads):**
| Config | read_file cap | Input size | Output | Time | Result |
|--------|--------------|------------|--------|------|--------|
| B | 200 | 3,748 chars | 3,328 chars | 24.7s | Excellent — full signatures |
| C-6k | 6,000 | 36,090 chars | 78 chars | 4.4s | **BROKEN** — continuation text |
| D-40k | 40,000 | 154,866 chars | 24,224 chars | 87.7s | **BROKEN** — kimi makes tool calls |

**Root cause:** When the input contains large blocks of raw code, kimi treats the input as
an in-progress coding task to continue rather than a conversation to summarize. It starts
generating tool calls (read_file, etc.) at any cap above ~3k chars per file.

**Key finding:** Agent messages ALREADY synthesize file contents — class signatures, method
names, and behavioral details appear in the assistant's text, not just the raw tool results.
Config B with 200-char caps extracts `IKChain(bones, solver=None)`, `FABRIKSolver(max_iterations=10, tolerance=0.01)`, etc. because the agent described these when it read the files.

**Result:** Kept `read_file` at 1500 chars. Cap increase is counterproductive with kimi.
The prompt change (Experiment 2) remains the primary quality improvement. ✅

**Eval data:**
- `52862e3f` — BROWSER_AGENT, 68 msgs, pure browser (click/open_url/read_page)
- `de4dcbd4` — BROWSER_AGENT, 61 msgs, browser + bash (run_bash_cmd)
- `2efdbdb2/TEST_RIG_CREATOR` — 68 msgs, pure code (grep/read_file/write_file/bash)

**Results:** See runner output below (fill in after running `run_prompt_eval.py`).
