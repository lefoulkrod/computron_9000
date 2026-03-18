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

## Removed (not needed)

| # | Name | Why removed |
|---|------|-------------|
| 3 | Reorder sections | Probes already pass for "what next" — agent finds remaining work fine. |
| 4 | Relax process suppression | Scenario 05 passes 4/4 — model already preserves failed approaches. |
| 7 | Conversation-type-aware prompts | No mixed results across scenario types. Single prompt works. |
| 8 | Structured output format | No evidence current format is a problem. High risk for no clear gain. |

## Future experiments

To be added as needed when new scenarios or real-world testing reveals gaps.
