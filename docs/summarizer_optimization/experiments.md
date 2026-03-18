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

### Experiment 12: Content-type filtering for low-value tool outputs

**What**: Detect and aggressively cap tool outputs that are filesystem dumps — `ls`, `find`, directory listings, file trees. These are low-information-density outputs that can dominate the summary when they're large.

**Discovered via**: Scenario 07 (real game creation). A `find *.html` output listed every HTML file on the filesystem (including pygame docs), and an `ls -la` listed every file in the home directory. These dominated the summary, drowning out the actual game creation work.

**Proposed change**: In `_serialize_messages`, detect tool results that look like directory listings (lines matching `drwx`, `-rw-`, or simple file-per-line patterns) and cap them at 2,000 chars instead of 10,000. The summarizer can still see the first ~50 files, but won't be overwhelmed by 500-line listings.

**Risk**: Medium. Might over-filter tool results that happen to look like directory listings but contain important data. Need careful pattern matching.
