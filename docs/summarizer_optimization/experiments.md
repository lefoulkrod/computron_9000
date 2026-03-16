# Experiments

Each experiment is tested in isolation against the current baseline. One change at a time. Results recorded in [`results.md`](results.md).

## Priority 1: Prompt structure changes

These are cheap to test (prompt-only, no code changes) and directly address known problems.

### Change 1: Remove `## User's Request` section

**What**: Remove the `## User's Request` heading and instructions from `_SUMMARIZE_PROMPT`. The summary starts with `## Remaining Work` or `## Completed Work` instead.

**Hypothesis**: The original user message is already pinned and always visible to the agent. Having the summarizer restate it wastes ~50-100 tokens and introduces a known failure mode where the model echoes the template instruction ("State the user's full original request...") instead of filling it in. Removing it gives the model more budget for actual facts.

**How to test**: Run all scenarios with the modified prompt. Check that fact retention stays the same or improves. Verify the agent can still identify the task goal from the pinned message.

**Risk**: Low. The pinned message is the authoritative source anyway.

### Change 2: Selective URL retention

**What**: Change "MUST INCLUDE every URL visited or discovered" to "MUST INCLUDE URLs needed to revisit results or continue work. Omit intermediate navigation URLs (search engines, category pages, filter/sort pages)."

**Hypothesis**: Many URLs are intermediate navigation (google.com, google.com/flights, amazon.com/s?k=...) that the agent never needs to revisit. Including them clutters the Key Data section and may crowd out more important facts. Focusing on result URLs (product pages, booking pages, data sources) improves signal-to-noise.

**How to test**: Run browser scenarios. Count result URLs retained vs intermediate URLs. Verify the agent can still navigate back to useful pages.

**Risk**: Medium. Some intermediate URLs might matter (e.g., a search page with specific filters that are hard to reconstruct). Test carefully with the flight search scenario.

### Change 3: Reorder sections — Remaining Work first

**What**: Change the section order from (User's Request → Completed Work → Key Data → Remaining Work) to (Remaining Work → Current State → Completed Work → Key Data). Or if Change 1 is accepted: (Remaining Work → Completed Work → Key Data).

**Hypothesis**: The agent reads top-to-bottom. The most actionable information — what to do next — should come first. Currently it's buried at the bottom after potentially hundreds of lines of completed work and data.

**How to test**: Run all scenarios. Check continuity probe scores (does the agent pick up the right next action more often?).

**Risk**: Low. The model generates all sections regardless of order.

## Priority 2: Content changes

These affect what the model preserves vs discards. Higher impact but also higher risk.

### Change 4: Relax process suppression for coding/desktop

**What**: Replace the blanket "omit HOW results were obtained" with a nuanced rule: "Omit UI navigation mechanics (clicks, scrolls, page loads). DO preserve: attempted approaches and their outcomes, especially failures. If a fix was tried and didn't work, say what was tried and why it failed."

**Hypothesis**: For coding and desktop agents, failed approaches are critical context. The agent needs to know "tried adding null check to line 42, tests still failed with TypeError" to avoid retrying the same approach. The current prompt treats this as "process narration" and discards it.

**How to test**: Run scenarios 03 (browser failures) and 05 (coding debug failures). These are specifically designed to test whether failed approaches survive compaction. Also run scenario 02 (desktop) to check GUI state is preserved.

**Risk**: Medium. The model may over-include process details for browser agents too. May need agent-type-specific prompts (Change 7) to get this right.

### Change 5: Add `## Current State` section

**What**: Add a new section to the prompt: "## Current State — describe the current state of the task: which application/page is open, what files are modified, what errors are unresolved, what the agent was about to do next."

**Hypothesis**: For stateful agents (desktop, coding, form filling), knowing WHERE you are is as important as knowing WHAT you've done. "Calculator is open, last result was 345" or "worker.py has been edited but tests haven't been run yet" is critical for continuity.

**How to test**: Run scenarios 02 (desktop), 04 (form filling), 05 (coding debug). Check whether the summary captures the current state accurately.

**Risk**: Low. Adds information without removing anything. May increase summary length slightly.

## Priority 3: Structural changes

These are larger changes that may require code modifications or prompt architecture changes.

### Experiment 6: Model size comparison

**What**: Run the full scenario suite across different sizes within the qwen3 family, then compare against a newer generation at the same size.

| Model | Size | Role |
|-------|------|------|
| `qwen3:8b` | 8B | Current production model (baseline) |
| `qwen3:4b` | 4B | Same family, smaller — does quality hold? |
| `qwen3:1.7b` | 1.7B | Same family, smallest — where does quality break? |
| `qwen3.5:4b` | 4B | Newer generation, same size as qwen3:4b — is newer better? |

Only after finding the optimal size within qwen3 should we test other architectures (glm, gemma, etc.). This isolates the model-size variable from the architecture variable.

**Hypothesis**: Smaller models are faster but may follow instructions worse. We need to find the quality floor — the smallest model that still produces useful summaries. If `qwen3:4b` is nearly as good as `qwen3:8b` but twice as fast, that's a win.

**How to test**: Run all scenarios with each model, 3 runs each. Compare fact retention, structure compliance, and time. Look for the quality cliff.

**Risk**: None — this is measurement, not a change. But results may motivate switching models.

### Experiment 7: Conversation-type-aware prompt selection

**What**: Instead of one `_SUMMARIZE_PROMPT` for all conversations, add a lightweight classification step that looks at the conversation content (tool names used, message patterns) and selects the best prompt variant. For example, a conversation full of `browse_page`/`click`/`fill_field` calls gets a browser-optimized prompt; one with `read_file`/`apply_text_patch`/`run_bash_cmd` gets a coding-optimized prompt.

**Hypothesis**: If earlier experiments show that a change helps some conversation types but hurts others, that's a signal that one prompt can't serve all types. A classifier that picks the right prompt per conversation would let us optimize each type independently without compromising the others.

**How to test**: First, run experiments 1-5 and check for mixed results across scenario types. If a pattern emerges (e.g., relaxing process suppression helps coding but hurts browser), build prompt variants and a simple classifier (could be as simple as "if tool names include `browse_page`, use browser prompt"). Run all scenarios with the classifier. Compare against best single-prompt results.

**Risk**: Added complexity — multiple prompts plus selection logic. Only worth pursuing if single-prompt experiments show clear type-dependent tradeoffs.

### Change 8: Structured output format

**What**: Replace the markdown heading format with a mechanical key-value format:
```
GOAL: [task description]
STATUS: [in progress / blocked / complete]
DONE:
- [completed items]
STATE:
- [current state]
DATA:
- [key data items]
TODO:
- [remaining work]
```

**Hypothesis**: Smaller models may follow a simpler format more reliably than markdown headings. The key-value format is also easier to parse programmatically if we ever want to extract specific sections.

**How to test**: Run all scenarios with the new format. Compare structure compliance and fact retention against the markdown format.

**Risk**: Medium. The agent prompt currently expects markdown summaries. Changing the format requires updating how the agent interprets compacted messages. Test last.
