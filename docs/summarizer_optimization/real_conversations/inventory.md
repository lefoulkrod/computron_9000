# Real Conversation Inventory

Source: `~/.computron_9000/conversations/summaries/*.json` (238 stored records, 17 with real content)

These records will be used for validation after we optimize the summarizer with synthetic scenarios. They capture real agent behavior with all its messiness, but we don't have full control over the data, so synthetics come first.

## Browser Agent — Flight Search (8 records, 2 original conversations)

| Record ID | Type | Msgs | Input chars | Quality | Description |
|-----------|------|------|-------------|---------|-------------|
| `f4d90714` | single | 71 | 22,542 | **Good** | AUS->ORD Apr 10-12, nonstop flight search |
| `877c008c` | merge | 53 | 14,868 | **Good** | Merge of f4d90714 — tests merge fidelity |
| `377be1ea` | merge | 36 | 11,030 | **Good** | 2-deep merge — tests fact accumulation |
| `d9c56f8d` | single | 62 | 19,768 | **Good** | 4-weekend trip search |
| `20dacc60` | merge | 39 | 12,898 | **Good** | Merge of d9c56f8d |
| `f0aa0d02` | merge | 37 | 12,344 | **Good** | 2-deep merge |
| `996fa44f` | merge | 75 | 22,345 | **Concerning** | 3-deep merge — summary is 5.4k chars. Growing summaries? |
| `a2e0601a` | merge | 39 | 11,592 | **Concerning** | 4-deep merge — summary is 6.3k chars |

**What they test well**: Snapshot dedup effectiveness, price/URL retention, merge fidelity across depths.
**What they don't test**: All are the same task type (flight search on Google Flights). No variety in browser interaction patterns.
**Continuity check**: After compaction, can the agent continue searching for the next trip/date range without re-asking user preferences?

## Browser Agent — Research (1 record)

| Record ID | Type | Msgs | Input chars | Quality | Description |
|-----------|------|------|-------------|---------|-------------|
| `3531a10f` | single | 114 | 32,712 | **Best record** | Chicago neighborhoods, hotels, restaurants |

**What it tests well**: Longest conversation, highest input chars. Good stress test for snapshot dedup and budget cap. Lots of URLs and data points.
**Continuity check**: After compaction, can the agent reference specific restaurants/hotels from earlier neighborhoods?

## Browser Agent — Shopping (4 records, same conversation)

| Record ID | Type | Msgs | Input chars | Quality | Description |
|-----------|------|------|-------------|---------|-------------|
| `2cff248c` | single | 9 | 2,349 | **Weak** | Amazon gaming laptops under $800 |
| `b0847bb9` | merge | 9 | 2,349 | **Weak** | Merge of above |
| `29c8b14a` | merge | 9 | 2,349 | **Weak** | Merge of above |
| `8d28f0d0` | merge | 9 | 2,349 | **Weak** | Merge of above |

**Problem**: 9 messages and 2.3k chars is too short to meaningfully exercise the pipeline. No snapshot dedup triggers. All 4 records have identical input size, suggesting the conversation didn't grow between compactions.
**Verdict**: Useful only as a trivial baseline.

## Desktop Agent (3 records, same conversation)

| Record ID | Type | Msgs | Input chars | Quality | Description |
|-----------|------|------|-------------|---------|-------------|
| `6613311c` | single | 14 | 1,274 | **Marginal** | Open calculator, perform calculation |
| `b6de6357` | merge | 3 | 102 | **Useless** | 102 chars of input — nothing to summarize |
| `b725c174` | merge | 3 | 586 | **Useless** | 586 chars — barely a sentence |

**Problem**: The merge records have so little input that the summarizer is generating from nothing.
**Verdict**: Only `6613311c` has enough substance to be worth testing.

## Coding Agent (1 record)

| Record ID | Type | Msgs | Input chars | Quality | Description |
|-----------|------|------|-------------|---------|-------------|
| `3ac63631` | single | 33 | 4,458 | **Decent** | Add pipe-entering mechanic to Mario game |

**What it tests**: File path retention, code snippet handling.
**What it doesn't test**: No errors, no retries, no multi-file changes.
**Continuity check**: After compaction, can the agent reference the files it modified?

## Records useful for testing (summary)

| Priority | Record ID | Why |
|----------|-----------|-----|
| Use first | `3531a10f` | Best stress test — 114 msgs, 32k chars |
| Use first | `f4d90714` | Good single compaction — 71 msgs |
| Use first | `877c008c` | Good merge test — 53 msgs |
| Use | `d9c56f8d`, `20dacc60`, `f0aa0d02` | Flight search variety |
| Investigate | `996fa44f`, `a2e0601a` | Growing summary size — potential compression failure |
| Use for coding | `3ac63631` | Only coding record |
| Skip | `2cff248c`, `b0847bb9`, `29c8b14a`, `8d28f0d0` | Too short |
| Skip | `b6de6357`, `b725c174` | Useless — negligible input |
| Marginal | `6613311c` | Only desktop record, but very simple |
