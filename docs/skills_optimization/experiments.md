# Experiments

Each experiment is tested in isolation against the current baseline. One change at a time. Results recorded in [`results.md`](results.md).

## Sprint 1: Foundation + Highest-ROI Fixes

| # | Name | Verdict | Notes |
|---|------|---------|-------|
| 1 | Framework + baseline | — | Build scenarios, runner, whitelist. Establish baseline scores. |
| 2 | Tool validation post-processing | — | Strip/reject skills with hallucinated tools. Deterministic fix. |
| 3 | Similarity-based dedup before save | — | Merge near-duplicates instead of creating separate entries. |
| 4 | Generalization prompt | — | Add naming rules + `{parameter}` placeholders to extraction prompts. |

## Sprint 2: Rejection + Search

| # | Name | Verdict | Notes |
|---|------|---------|-------|
| 5 | Hard rejection rules | — | Reject <3 steps, delegation-only, single-tool-repeat patterns. |
| 6 | Better search matching | — | Replace substring match with keyword similarity scoring in `search_skills()`. |
| 7 | Parametrized step descriptions | — | Strengthen prompt to require `{param}` placeholders in step descriptions. |

## Sprint 3: Refinement

| # | Name | Verdict | Notes |
|---|------|---------|-------|
| 8 | LLM-based dedup | — | If experiment 3 insufficient: ask LLM "same workflow?" for ambiguous matches. |
| 9 | Extraction model comparison | — | Test mistral:7b, qwen3:8b, qwen3.5:cloud. Measurement only. |

---

## Experiment Details

### Experiment 1: Framework + Baseline

**What**: Set up the experiment framework (scenarios, runner, whitelist). Run all 7 scenarios 3x with the current extractor unchanged.

**Files to create**:
- `docs/skills_optimization/run_scenarios.py` — standalone runner
- `docs/skills_optimization/scenarios/01_browser_product_search.md` — EXTRACT scenario
- `docs/skills_optimization/scenarios/02_browser_form_workflow.md` — EXTRACT scenario
- `docs/skills_optimization/scenarios/03_github_repo_creation.md` — EXTRACT scenario
- `docs/skills_optimization/scenarios/04_coding_multi_step.md` — EXTRACT scenario
- `docs/skills_optimization/scenarios/05_trivial_qa_reject.md` — REJECT scenario
- `docs/skills_optimization/scenarios/06_delegation_only_reject.md` — REJECT scenario
- `docs/skills_optimization/scenarios/07_duplicate_merge.md` — EXTRACT + dedup scenario

**Expected result**: Baseline numbers showing duplication rate, hallucinated tool rate, false extraction rate.

---

### Experiment 2: Tool Validation Post-Processing

**What**: After extraction, validate every `step.tool` against the tool whitelist for the skill's `agent_scope`. Strip invalid steps; reject skill if >50% stripped.

**File**: `skills/_extractor.py`

**Change**: Add `_validate_skill(skill: SkillDefinition) -> SkillDefinition | None` called after `_parse_skill_json()` in both `_analyze_conversation()` (line ~491) and `_analyze_sub_agent()` (line ~567).

**Risk**: Very low. Deterministic, no LLM behavior change.

**Expected impact**: Tool validity 100%. Some current skills (e.g., `comprehensive_travel_planner`) would be rejected.

---

### Experiment 3: Similarity-Based Dedup Before Save

**What**: Before `add_skill()`, compute `_keyword_similarity()` between new skill and all existing skills. If similarity > 0.4, merge `source_conversations` into existing skill instead of creating new entry.

**File**: `skills/_extractor.py` (`_try_save_skill()`)

**Risk**: Medium. Threshold may need tuning — too aggressive merges unrelated skills, too weak still duplicates.

**Expected impact**: Skill count drops from 27 to ~12-15. eBay cluster (8 skills) collapses to 1-2. GitHub cluster (4 skills) collapses to 1.

---

### Experiment 4: Generalization Prompt

**What**: Add explicit naming rules to extraction prompts: general pattern names, not instance-specific names. Add `{parameter}` placeholder guidance.

**File**: `skills/_extractor.py` (both `_CONVERSATION_EXTRACTION_PROMPT` and `_BROWSER_EXTRACTION_PROMPT`)

**Prompt addition**:
```
NAMING RULES:
- The skill name must describe the GENERAL pattern, not the specific instance.
  Good: "ebay_product_research", "google_flights_search"
  Bad: "enterprise_cpu_price_spec_research", "high_wattage_psu_research_workflow"
- Replace specific products, brands, or queries with generic terms in the name.
- In step descriptions, use {parameter} placeholders for values that change:
  Good: "Search {site} for {query}"
  Bad: "Search eBay for AMD Threadripper Pro 7995WX"
```

**Risk**: Low. Model might over-generalize. Usefulness probes catch this.

---

### Experiment 5: Hard Rejection Rules

**What**: Post-extraction hard rejection rules:
1. Reject if < 3 steps
2. Reject if >50% of steps use delegation tools (`browser_agent_tool`, `computer_agent_tool`, etc.)
3. Reject if all steps use the same tool

**File**: `skills/_extractor.py`

**Risk**: Low. Might over-reject edge cases (legitimate 2-step skills are rare).

---

### Experiment 6: Better Search Matching

**What**: Replace `any(k in haystack for k in keywords)` with `_keyword_similarity(query, haystack) > 0.15`, sorted by score descending.

**File**: `skills/_registry.py` (`search_skills()`, line 117)

**Risk**: Very low. Simple function swap.

**Expected impact**: Skills actually get found when agents search. Addresses zero-usage problem.

---

### Experiment 7: Parametrized Step Descriptions

**What**: Strengthen step construction guidelines to require `{curly_brace}` placeholders for variable values.

**File**: `skills/_extractor.py` (extraction prompts)

**Risk**: Low. Model might add too many parameters or use inconsistent naming.

---

### Experiment 8: LLM-Based Dedup (if needed)

**What**: For ambiguous similarity range (0.2-0.5), ask extraction model "Is this the same workflow? YES/NO."

**File**: `skills/_extractor.py`

**Risk**: Cost — N LLM calls per extraction. Only implement if experiment 3 leaves significant duplication.

---

### Experiment 9: Extraction Model Comparison

**What**: Run all scenarios against `mistral:7b`, `qwen3:8b`, `qwen3.5:cloud`. Measurement only.

**Risk**: None (measurement only).
