# Skills Extractor Optimization Plan

## Context

The skills extractor (`skills/_extractor.py`) analyzes stored conversations to extract reusable workflow recipes. It has the infrastructure in place (two-phase extraction, background loop, registry, agent-facing tools) but the quality of extracted skills is poor:

- **Massive duplication**: 8 eBay search skills, 4 GitHub repo creation skills, 2 Google Flights skills (27 total, should be ~10)
- **Hallucinated tools**: Skills reference nonexistent tools (`browser_interaction_loop`, `generate_pdf_itinerary`, `answer`, `run_browser_agent_as_tool`)
- **Weak rejection**: `comprehensive_travel_planner` uses delegation tools as steps — exactly what the prompt says to reject
- **Over-specific naming**: `enterprise_cpu_price_spec_research` instead of `ebay_product_research`
- **Zero usage**: All 27 skills have `usage_count: 0` — the keyword search in `_registry.py` is too crude to surface relevant matches
- **No dedup/merge logic**: `_try_save_skill()` only merges if exact name matches; near-duplicates get separate entries

We'll follow the same experiment-driven approach used for the summarizer optimization (`docs/summarizer_optimization/`): synthetic scenarios with automated scoring, one change at a time, 3 runs minimum per experiment.

## 1. Goal

**Skill extraction quality**: the extractor should produce a small set of general, accurate, non-duplicated skills with valid tool references that agents can actually find and use.

## 2. Scope

This optimization targets the extraction pipeline in `skills/_extractor.py` (prompts, post-processing, dedup logic) and the search mechanism in `skills/_registry.py`. The background loop machinery, agent integration hooks, and skill data model are out of scope unless experiments reveal they need changes.

## 3. Current Algorithm (Baseline)

**File**: `skills/_extractor.py`

### Two-Phase Extraction
- **Phase 1 (Analyze)**: Feed full untruncated conversation transcript to LLM. Output: structured analysis (goal, golden path, struggles, site quirks).
- **Phase 2 (Extract)**: Feed Phase 1 analysis (or truncated transcript as fallback) to extraction prompt. Output: JSON skill definition or "NO".

### Prompts
- `_ANALYSIS_PROMPT` — Phase 1, produces structured analysis
- `_CONVERSATION_EXTRACTION_PROMPT` — Phase 2, generic workflow extraction
- `_BROWSER_EXTRACTION_PROMPT` — Phase 2, browser-specific extraction
- `_REFINEMENT_PROMPT` — updates existing skills based on new usage

### Save Logic (`_try_save_skill`)
- Checks if skill with same exact name exists
- If yes: merge `source_conversations`, overwrite
- If no: add as new skill
- No similarity-based dedup — near-duplicates with different names get separate entries

### Search (`_registry.py:search_skills`)
- Splits query into keywords
- Matches if ANY single keyword is a substring of `name + description + trigger_patterns`
- No relevance ranking, no similarity scoring

### Model
- Extraction model: `qwen3.5:cloud` (configured in `config.yaml`)
- Context: 60,000 tokens, temperature 0.3

## 4. Test Strategy

### Method

**Scientific approach — one change at a time.** For each proposed change:
1. Run all scenarios against the current baseline
2. Apply exactly one change
3. Re-run all scenarios (minimum 3 runs)
4. Record results in `results.md`
5. Keep or discard based on metrics
6. If kept, it becomes the new baseline

### Scenarios

Each scenario defines a conversation and an expected outcome:

**EXTRACT scenarios** — should produce a skill. Include:
- Required properties (regexes on skill name, description, agent_scope)
- Valid tool assertions (every step.tool must be in the agent's real tool list)
- Forbidden tool list (hallucinated names that must NOT appear)
- Usefulness probes (LLM-as-judge questions about the extracted plan)

**REJECT scenarios** — should produce `NO`. Any extracted skill is a failure.

Scenario files: [`scenarios/`](scenarios/)

### Scoring

Primary metric: **correctness** — `(correct_extractions + correct_rejections) / total_scenarios`

Per extracted skill, secondary metrics:
- **Tool validity**: % of steps with real tool names for the declared scope
- **Fact retention**: required properties found in skill JSON
- **Usefulness probes**: pass rate (LLM-as-judge with pass/fail patterns)

Priority: **correctness > tool validity > usefulness probes**

### What constitutes a full run

- Run **all scenarios** (not just the target)
- Run each scenario **at least 3 times** for non-determinism
- Use `--save` to capture extracted skills and probe responses
- Report per-scenario and aggregate scores

Command: `PYTHONPATH=. uv run python docs/skills_optimization/run_scenarios.py --runs 3 --save`

### Anti-regression

A change is **kept** if:
- All REJECT scenarios still produce `NO`
- All EXTRACT scenarios still produce a skill (or improve)
- Tool validity does not regress
- Usefulness probes do not regress

A change is **discarded** if:
- A REJECT scenario starts producing a skill (false positive)
- An EXTRACT scenario stops producing a skill (sensitivity regression)
- Tool validity drops

## 5. Tool Whitelist

Derived from actual agent tool registrations in `agents/*/agent.py`:

| Scope | Valid tools |
|-------|-----------|
| BROWSER_AGENT | `open_url`, `browse_page`, `read_page`, `click`, `press_and_hold`, `perform_visual_action`, `fill_field`, `press_keys`, `select_option`, `scroll_page`, `go_back`, `drag`, `inspect_page`, `execute_javascript`, `save_page_content`, `run_bash_cmd`, `save_to_scratchpad`, `recall_from_scratchpad`, `lookup_skills`, `apply_skill` |
| COMPUTER_AGENT | `read_file`, `grep`, `list_dir`, `write_file`, `apply_text_patch`, `replace_in_file`, `run_bash_cmd`, `describe_image`, `save_to_scratchpad`, `recall_from_scratchpad`, `lookup_skills`, `apply_skill` |
| COMPUTRON_9000 | `run_bash_cmd`, `computer_agent_tool`, `browser_agent_tool`, `desktop_agent_tool`, `generate_media`, `create_custom_tool`, `lookup_custom_tools`, `run_custom_tool`, `output_file`, `play_audio`, `describe_image`, `run_sub_agent`, `remember`, `forget`, `lookup_skills`, `apply_skill` |
| DESKTOP_AGENT | `read_screen`, `describe_screen`, `mouse_click`, `mouse_double_click`, `mouse_drag`, `keyboard_type`, `keyboard_press`, `scroll`, `run_bash_cmd` |

Known hallucinated tools in current registry: `answer`, `browser_interaction_loop`, `generate_pdf_itinerary`, `run_browser_agent_as_tool` (actual name is `browser_agent_tool`, COMPUTRON_9000 scope only).

## 6. Experiments

Prioritized in [`experiments.md`](experiments.md). Results recorded in [`results.md`](results.md).
